from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from dataclasses import replace
from threading import Barrier

from exchange.catalog import load_by_issue, load_receipt
from exchange.codec import decode_packet, encode_packet, packet_digest
from exchange.intake import receive
from exchange.issue import issue
from ledger import InvalidInput, UnknownRecord, open_center
from register.revisions import load_revision
from sampling.design import load_design
from tests.fixtures import LedgerFixture, counts


class TestExchange(LedgerFixture):
    def test_repeat_receive(self):
        design = self.design('甲班', {'local-x': ('x', 12)}, {'rack': ('local-x',)}, {'rack': 1})
        number, wire = issue(self.station, design)
        receipt_id = receive(self.center, number, wire)
        self.detach()
        self.reopen_center()
        self.assertEqual(receive(self.center, number, wire), receipt_id)
        batch = load_receipt(self.center, receipt_id)
        self.assertEqual(batch, load_by_issue(self.center, number))
        self.assertEqual(batch.wire, wire)
        self.assertEqual(batch.packet.design_id, design)
        self.assertEqual(counts(self.center, 'intake'), {'intake': 1})

    def test_detached_evidence(self):
        design = self.design(
            '甲班', {'rig-a-only-normal': (None, 570201), 'rig-a-only-abnormal': (None, 1500203), 'rig-shared-x': ('x', 1400206)},
            {'rack': ('rig-a-only-normal', 'rig-a-only-abnormal', 'rig-shared-x'), 'idle': ()},
            {'rack': 2, 'idle': 0}, threshold=999999,
        )
        revision_id = load_design(self.station, design).revision_id
        revision = load_revision(self.station, revision_id)
        key = next(row.specimen.shared_key for row in revision.observations if row.specimen.shared_key is not None)
        number, wire = issue(self.station, design)
        receipt_id = receive(self.center, number, wire)
        self.detach()
        self.assertEqual(receive(self.center, number, wire), receipt_id)
        batch = load_receipt(self.center, receipt_id)
        self.assertEqual((batch.packet.revision_id, batch.packet.protocol_version), (revision_id, 'v1'))
        layers = {layer.name: layer for layer in batch.packet.evidence.layers}
        self.assertEqual((layers['idle'].quota, layers['idle'].size), (0, 0))
        rack = layers['rack']
        self.assertEqual((rack.quota, rack.private_normal, rack.private_abnormal), (2, 1, 1))
        self.assertEqual([(mark.key, mark.abnormal) for mark in rack.shared], [(key, True)])
        self.assertEqual(batch.digest, packet_digest(batch.packet))
        for private in (
            b'rig-a-only-normal', b'rig-a-only-abnormal', b'rig-shared-x',
            b'570201', b'1500203', b'1400206',
        ):
            self.assertNotIn(private, wire.split(b',"sha256":', 1)[0])

    def test_conflicting_issue(self):
        design = self.design('甲班', {'a': (None, 0)}, {'rack': ('a',)}, {'rack': 1})
        number, wire = issue(self.station, design)
        receipt_id = receive(self.center, number, wire)
        original = load_receipt(self.center, receipt_id)
        layer, = original.packet.evidence.layers
        altered = replace(layer, private_normal=0, private_abnormal=1)
        changed_evidence = replace(original.packet.evidence, layers=(altered,))
        conflict = encode_packet(replace(original.packet, evidence=changed_evidence))
        self.assertNotEqual(conflict, wire)
        self.assertEqual(decode_packet(conflict).issue_id, number)
        with self.assertRaisesRegex(InvalidInput, 'different packet'):
            receive(self.center, number, conflict)
        self.assertEqual(counts(self.center, 'intake'), {'intake': 1})
        self.assertEqual(load_receipt(self.center, receipt_id), original)

    def test_damaged_packet(self):
        design = self.design('甲班', {'a': (None, 0)}, {'rack': ('a',)}, {'rack': 1})
        number, wire = issue(self.station, design)
        receipt_id = receive(self.center, number, wire)
        original = load_receipt(self.center, receipt_id)
        altered_quota = wire.replace(b'"quota":1', b'"quota":0', 1)
        self.assertNotEqual(wire, altered_quota)
        for outer_number, packet in ((number, altered_quota), (number, wire[:-1]), ('other-issue', wire)):
            with self.subTest(issue=outer_number, packet=packet), self.assertRaises(InvalidInput):
                receive(self.center, outer_number, packet)
        self.assertEqual(counts(self.center, 'intake'), {'intake': 1})
        self.assertEqual(load_receipt(self.center, receipt_id), original)

    def test_concurrent_replay(self):
        design = self.design('甲班', {'a': (None, 0)}, {'rack': ('a',)}, {'rack': 1})
        shipment = issue(self.station, design)
        self.detach()
        ready = Barrier(2)

        def deliver():
            with closing(open_center(self.center_path)) as center:
                ready.wait(timeout=20)
                return receive(center, *shipment)

        with ThreadPoolExecutor(max_workers=2) as pool:
            left = pool.submit(deliver)
            right = pool.submit(deliver)
            first, second = left.result(), right.result()
        self.assertEqual(first, second)
        self.assertEqual(counts(self.center, 'intake'), {'intake': 1})
        self.assertEqual(load_receipt(self.center, first).wire, shipment[1])

    def test_unknown_design_does_not_issue(self):
        with self.assertRaises(UnknownRecord):
            issue(self.station, 1)
        self.assertEqual(counts(self.station, 'issued_batches'), {'issued_batches': 0})
