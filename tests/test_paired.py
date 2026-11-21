"""Regression for the version-2 paired review extension."""
from contextlib import closing
from dataclasses import replace
from fractions import Fraction
import sqlite3

from analysis.risk import publish, publish_pair
from exchange.catalog import load_by_issue, load_receipt
from exchange.issue import issue
from exchange.intake import receive
from exchange.paired_codec import decode_paired_packet, encode_paired_packet
from exchange.paired_issue import issue_pair
from ledger import InvalidInput, UnknownRecord, open_center
from register.revisions import revise
from report.paired_retrieve import read_pair
from report.retrieve import read
from samples.paired_inputs import private_inputs, shared_inputs
from sampling.design import freeze
from tests.fixtures import LedgerFixture, REPORT_TABLES, counts


PAIR_TABLES = REPORT_TABLES + ('pair_report_cells', 'report_parent_designs')


def _prepare(fixture, builder):
    designs = builder(fixture.station, fixture.station)
    return designs


class TestPairedIssue(LedgerFixture):
    def _private(self):
        return private_inputs(self.station, self.station)

    def test_kept_and_swapped_pairing(self):
        designs = self._private()
        kept_issue, kept_wire = issue_pair(self.station, designs['old'], designs['kept'])
        swapped_issue, swapped_wire = issue_pair(
            self.station, designs['old'], designs['swapped']
        )
        self.assertNotEqual(kept_issue, swapped_issue)
        packet = decode_paired_packet(kept_wire)
        self.assertEqual(packet.issue_id, kept_issue)
        self.assertEqual(packet.shift_id, '甲班')
        self.assertEqual((packet.old_design_id, packet.new_design_id), (designs['old'], designs['kept']))
        self.assertEqual(packet.evidence.layers[0].quota, 1)
        # Private pieces stay on the station: no local labels or readings in the wire.
        for secret in (b'plate-a', b'plate-b'):
            self.assertNotIn(secret, kept_wire)
        receipt = receive(self.center, kept_issue, kept_wire)
        self.detach()
        # Replay of the same canonical piece reuses the receipt number.
        self.assertEqual(receive(self.center, kept_issue, kept_wire), receipt)
        received = load_receipt(self.center, receipt)
        self.assertTrue(received.is_paired)
        self.assertEqual(load_by_issue(self.center, kept_issue).wire, kept_wire)
        self.assertEqual(counts(self.center, 'intake'), {'intake': 1})

    def test_same_count_swapped_physical_pieces_rejected(self):
        designs = self._private()
        before = counts(self.station, 'issued_batches', 'pair_issue_designs')
        with self.assertRaisesRegex(InvalidInput, 'swaps physical pieces'):
            issue_pair(self.station, designs['old'], designs['replaced'])
        self.assertEqual(counts(self.station, 'issued_batches', 'pair_issue_designs'), before)

    def test_layer_and_quota_mismatch_rejected(self):
        revision_a = self.design(
            '甲班', {'a': (None, 0), 'b': (None, 1)},
            {'rack': ('a', 'b')}, {'rack': 1},
        )
        revision_b = self.design(
            '乙班', {'a': (None, 0), 'b': (None, 1)},
            {'rack': ('a', 'b')}, {'rack': 1},
        )
        with self.assertRaises(InvalidInput):
            issue_pair(self.station, revision_a, revision_b)
        changed_quota = self.design(
            '甲班', {'a': (None, 0), 'b': (None, 1)},
            {'rack': ('a', 'b')}, {'rack': 2},
        )
        with self.assertRaises(InvalidInput):
            issue_pair(self.station, revision_a, changed_quota)

    def test_shared_identity_with_different_local_labels_pairs(self):
        designs = shared_inputs(self.station, self.station)
        issue_id, wire = issue_pair(self.station, designs['old'], designs['new'])
        packet = receive and decode_paired_packet(wire)
        self.assertEqual(packet.issue_id, issue_id)
        layer, = packet.evidence.layers
        marks = {mark.key: mark for mark in layer.shared}
        x_mark = next(mark for mark in marks.values())
        self.assertEqual((x_mark.old_abnormal, x_mark.new_abnormal), (False, True))
        self.assertEqual(len(marks), 1)

    def test_unknown_and_boolean_design_numbers(self):
        designs = self._private()
        with self.assertRaises(UnknownRecord):
            issue_pair(self.station, designs['old'], 999)
        for bad in (True, False, 0, -1):
            with self.subTest(bad=bad), self.assertRaises(InvalidInput):
                issue_pair(self.station, bad, designs['kept'])


class TestPairedIntake(LedgerFixture):
    def test_damaged_and_conflicting_paired_pieces(self):
        designs = private_inputs(self.station, self.station)
        issue_id, wire = issue_pair(self.station, designs['old'], designs['kept'])
        receipt_id = receive(self.center, issue_id, wire)
        original = load_receipt(self.center, receipt_id)
        damaged = wire.replace(b'"quota":1', b'"quota":0', 1)
        self.assertNotEqual(damaged, wire)
        for delivered_id, piece in (
            (issue_id, damaged),
            (issue_id, wire[:-1]),
            ('other-issue', wire),
        ):
            with self.subTest(delivered=delivered_id), self.assertRaises(InvalidInput):
                receive(self.center, delivered_id, piece)
        altered = replace(
            original.packet, old_design_id=original.packet.new_design_id
        )
        conflict = encode_paired_packet(altered)
        self.assertNotEqual(conflict, wire)
        with self.assertRaisesRegex(InvalidInput, 'different packet'):
            receive(self.center, issue_id, conflict)
        self.assertEqual(counts(self.center, 'intake'), {'intake': 1})
        self.assertEqual(load_receipt(self.center, receipt_id), original)


class TestPairedPublication(LedgerFixture):
    def _private_published(self, second_name, m=2):
        designs = private_inputs(self.station, self.station)
        pair_id, pair_wire = issue_pair(self.station, designs['old'], designs[second_name])
        other_id, other_wire = issue(self.station, designs['other'])
        pair_receipt = receive(self.center, pair_id, pair_wire)
        other_receipt = receive(self.center, other_id, other_wire)
        return publish_pair(self.center, pair_receipt, other_receipt, m), pair_receipt, other_receipt

    def test_private_table_values(self):
        kept, _, _ = self._private_published('kept')
        self.assertEqual(kept.record.status, 'reachable')
        self.assertEqual(kept.record.condition_mass, Fraction(1))
        self.assertEqual(kept.record.probabilities, (Fraction(1, 2), Fraction(0), Fraction(0), Fraction(1, 2)))
        swapped, _, _ = self._private_published('swapped')
        self.assertEqual(swapped.record.probabilities, (Fraction(0), Fraction(1, 2), Fraction(1, 2), Fraction(0)))

    def test_shared_table_values_and_parents(self):
        designs = shared_inputs(self.station, self.station)
        pair_id, pair_wire = issue_pair(self.station, designs['old'], designs['new'])
        other_id, other_wire = issue(self.station, designs['other'])
        pair_receipt = receive(self.center, pair_id, pair_wire)
        other_receipt = receive(self.center, other_id, other_wire)
        cases = {
            1: (Fraction(1, 6), (Fraction(0), Fraction(1), Fraction(0), Fraction(0))),
            2: (Fraction(5, 6), (Fraction(2, 5), Fraction(1, 5), Fraction(2, 5), Fraction(0))),
        }
        for m, (mass, cells) in cases.items():
            signed = publish_pair(self.center, pair_receipt, other_receipt, m)
            self.assertEqual((signed.record.condition_mass, signed.record.probabilities), (mass, cells))
            self.assertEqual(read_pair(self.center, signed.record.report_id), signed)
        unreachable = publish_pair(self.center, pair_receipt, other_receipt, 3)
        self.assertEqual(unreachable.record.status, 'unreachable')
        self.assertEqual(unreachable.record.condition_mass, Fraction(0))
        self.assertIsNone(unreachable.record.probabilities)
        first = read_pair(self.center, unreachable.record.report_id)
        self.assertEqual(first, unreachable)
        first_parent, second_parent = first.parents
        self.assertEqual(first_parent.receipt_id, pair_receipt)
        self.assertEqual(first_parent.shift_id, '甲班')
        self.assertEqual(first_parent.digest, load_receipt(self.center, pair_receipt).digest)
        self.assertEqual(
            [(design.design_id, design.revision_id, design.protocol_version) for design in first_parent.designs],
            [
                (designs['old'], load_receipt(self.center, pair_receipt).packet.old_revision_id, 'inspection'),
                (designs['new'], load_receipt(self.center, pair_receipt).packet.new_revision_id, 'inspection'),
            ],
        )
        self.assertEqual(second_parent.receipt_id, other_receipt)
        self.assertEqual(second_parent.shift_id, '乙班')
        self.assertEqual(len(second_parent.designs), 1)
        self.assertEqual(second_parent.designs[0].design_id, designs['other'])
        self.assertTrue(first.receipt.token)
        self.assertEqual(first.receipt.report_id, unreachable.record.report_id)

    def test_parent_type_order_and_shift_validation(self):
        designs = shared_inputs(self.station, self.station)
        pair_id, pair_wire = issue_pair(self.station, designs['old'], designs['new'])
        other_id, other_wire = issue(self.station, designs['other'])
        pair_receipt = receive(self.center, pair_id, pair_wire)
        other_receipt = receive(self.center, other_id, other_wire)
        # Reversed or wrong-typed parents are invalid requests.
        with self.assertRaises(InvalidInput):
            publish_pair(self.center, other_receipt, pair_receipt, 1)
        with self.assertRaises(InvalidInput):
            publish_pair(self.center, pair_receipt, pair_receipt, 1)
        # Same shift: pair a V1 of 甲班 with the paired 甲班 batch.
        same_shift = receive(self.center, *issue(self.station, designs['old']))
        with self.assertRaises(InvalidInput):
            publish_pair(self.center, pair_receipt, same_shift, 1)

    def test_unknown_receipts_and_invalid_m(self):
        designs = private_inputs(self.station, self.station)
        pair_receipt = receive(self.center, *issue_pair(self.station, designs['old'], designs['kept']))
        other_receipt = receive(self.center, *issue(self.station, designs['other']))
        with self.assertRaises(UnknownRecord):
            publish_pair(self.center, 999, other_receipt, 2)
        with self.assertRaises(UnknownRecord):
            publish_pair(self.center, pair_receipt, 999, 2)
        before = counts(self.center, *PAIR_TABLES)
        for bad in (True, False, -1, 1.0, '2', None):
            with self.subTest(bad=bad), self.assertRaises(InvalidInput):
                publish_pair(self.center, pair_receipt, other_receipt, bad)
        self.assertEqual(counts(self.center, *PAIR_TABLES), before)

    def test_failed_write_is_retryable_without_extra_records(self):
        designs = private_inputs(self.station, self.station)
        pair_receipt = receive(self.center, *issue_pair(self.station, designs['old'], designs['kept']))
        other_receipt = receive(self.center, *issue(self.station, designs['other']))
        self.detach()
        before = counts(self.center, *PAIR_TABLES)
        self.center.execute(
            "CREATE TRIGGER reject_pair_receipt BEFORE INSERT ON report_receipts "
            "BEGIN SELECT RAISE(ABORT, 'receipt ledger is closed'); END"
        )
        with self.assertRaisesRegex(sqlite3.IntegrityError, 'receipt ledger is closed'):
            publish_pair(self.center, pair_receipt, other_receipt, 2)
        self.reopen_center()
        self.assertEqual(counts(self.center, *PAIR_TABLES), before)
        self.center.execute('DROP TRIGGER reject_pair_receipt')
        signed = publish_pair(self.center, pair_receipt, other_receipt, 2)
        self.assertEqual(signed.record.probabilities, (Fraction(1, 2), Fraction(0), Fraction(0), Fraction(1, 2)))
        after = counts(self.center, *PAIR_TABLES)
        self.assertEqual(after['reports'], before['reports'] + 1)
        self.assertEqual(after['report_receipts'], before['report_receipts'] + 1)
        self.assertEqual(after['pair_report_cells'], before['pair_report_cells'] + 4)
        self.assertEqual(after['report_parent_designs'], before['report_parent_designs'] + 3)

    def test_reopen_and_corrections_keep_original(self):
        designs = shared_inputs(self.station, self.station)
        pair_receipt = receive(self.center, *issue_pair(self.station, designs['old'], designs['new']))
        other_receipt = receive(self.center, *issue(self.station, designs['other']))
        original = publish_pair(self.center, pair_receipt, other_receipt, 2)
        self.detach()
        self.reopen_center()
        self.assertEqual(read_pair(self.center, original.record.report_id), original)
        # Pair reports live in their own number space of the retrieval API.
        self.assertIsNone(read(self.center, original.record.report_id))
        self.assertIsNone(read_pair(self.center, 999))

    def test_other_shift_private_abnormal_sets_both_version_bits(self):
        # A always draws one piece normal under both versions; no shared keys.
        old = self.design(
            '甲班', {'a': (None, 0), 'd': (None, 1)},
            {'rack': ('a', 'd')}, {'rack': 1},
        )
        new = self.design(
            '甲班', {'a': (None, 1), 'd': (None, 0)},
            {'rack': ('a', 'd')}, {'rack': 1},
        )
        right = self.design(
            '乙班', {'b': (None, 0), 'c': (None, 12)},
            {'rack': ('b', 'c')}, {'rack': 1},
        )
        pair_receipt = receive(self.center, *issue_pair(self.station, old, new))
        other_receipt = self.ship(right)
        self.detach()
        signed = publish_pair(self.center, pair_receipt, other_receipt, 2)
        # Half of B's draws are abnormal, which counts under both versions;
        # the other half leaves both versions without any detection.
        self.assertEqual(signed.record.condition_mass, Fraction(1))
        self.assertEqual(signed.record.probabilities, (Fraction(1, 2), Fraction(0), Fraction(0), Fraction(1, 2)))

    def test_other_shift_private_mixed_cells(self):
        # A flips one private piece between versions; B half abnormal, half normal.
        old = self.design(
            '甲班', {'a': (None, 0), 'd': (None, 12)},
            {'rack': ('a', 'd')}, {'rack': 1},
        )
        new = self.design(
            '甲班', {'a': (None, 12), 'd': (None, 0)},
            {'rack': ('a', 'd')}, {'rack': 1},
        )
        right = self.design(
            '乙班', {'b': (None, 0), 'c': (None, 12)},
            {'rack': ('b', 'c')}, {'rack': 1},
        )
        pair_receipt = receive(self.center, *issue_pair(self.station, old, new))
        other_receipt = self.ship(right)
        self.detach()
        signed = publish_pair(self.center, pair_receipt, other_receipt, 2)
        self.assertEqual(
            signed.record.probabilities,
            (Fraction(0), Fraction(1, 4), Fraction(1, 4), Fraction(1, 2)),
        )

    def test_empty_draws_m_zero(self):
        left = self.design('甲班', {'a': (None, 10)}, {'empty': ()}, {'empty': 0})
        right = self.design('乙班', {'b': (None, 10)}, {'unused': ()}, {'unused': 0})
        pair_receipt = receive(self.center, *issue_pair(self.station, left, left))
        other_receipt = self.ship(right)
        signed = publish_pair(self.center, pair_receipt, other_receipt, 0)
        self.assertEqual(signed.record.condition_mass, Fraction(1))
        self.assertEqual(signed.record.probabilities, (Fraction(1), Fraction(0), Fraction(0), Fraction(0)))


class TestPairedLifecycle(LedgerFixture):
    def test_erratum_and_reopen_keep_original_by_number(self):
        designs = shared_inputs(self.station, self.station)
        pair_receipt = receive(self.center, *issue_pair(self.station, designs['old'], designs['new']))
        other_receipt = receive(self.center, *issue(self.station, designs['other']))
        original = publish_pair(self.center, pair_receipt, other_receipt, 2)
        original_id = original.record.report_id
        # A later erratum and a fresh frozen design never alter the signed number.
        revision = revise(self.station, '甲班', {'x-after': ('x', 0)})
        corrected = freeze(
            self.station, '甲班', revision, 'inspection',
            {'rack': ('x-after', 'a', 'c')}, {'rack': 1},
        )
        new_pair = receive(self.center, *issue_pair(self.station, designs['new'], corrected))
        self.detach()
        self.reopen_center()
        self.assertEqual(read_pair(self.center, original_id), original)
        # A new paired report signed after the erratum gets its own number.
        newer = publish_pair(self.center, new_pair, other_receipt, 2)
        self.assertNotEqual(newer.record.report_id, original_id)
        self.reopen_center()
        self.assertEqual(read_pair(self.center, original_id), original)
        self.assertEqual(read_pair(self.center, newer.record.report_id), newer)

    def test_replay_from_another_center_connection(self):
        designs = private_inputs(self.station, self.station)
        shipment = issue_pair(self.station, designs['old'], designs['kept'])
        first = receive(self.center, *shipment)
        self.detach()
        with closing(open_center(self.center_path)) as reopened:
            self.assertEqual(receive(reopened, *shipment), first)
            self.assertEqual(load_by_issue(reopened, shipment[0]).receipt_id, first)
        self.assertEqual(counts(self.center, 'intake'), {'intake': 1})

    def test_multilayer_and_zero_quota_pair(self):
        old = self.design(
            '甲班',
            {'x': ('x', 12), 'a': (None, 0), 'y': ('y', 0), 'b': (None, 12)},
            {'lower': ('x', 'a'), 'upper': ('y', 'b')},
            {'lower': 1, 'upper': 1},
        )
        new = self.design(
            '甲班',
            {'x': ('x', 0), 'a': (None, 12), 'y': ('y', 0), 'b': (None, 0)},
            {'lower': ('x', 'a'), 'upper': ('y', 'b')},
            {'lower': 1, 'upper': 1},
        )
        right = self.design(
            '乙班', {'X': ('x', 0), 'Y': ('y', 0)}, {'rack': ('X', 'Y')}, {'rack': 1}
        )
        pair_receipt = receive(self.center, *issue_pair(self.station, old, new))
        other_receipt = self.ship(right)
        self.detach()
        signed = publish_pair(self.center, pair_receipt, other_receipt, 2)
        self.assertEqual(signed.record.status, 'reachable')
        self.assertTrue(sum(signed.record.probabilities) == Fraction(1))
        self.assertEqual(signed.record.condition_mass, Fraction(1, 2))
        # Both versions keep their own margins: old misses 3/4, new misses 1/4.
        margins = (
            signed.record.probabilities[2] + signed.record.probabilities[3],
            signed.record.probabilities[1] + signed.record.probabilities[3],
        )
        self.assertEqual(margins, (Fraction(3, 4), Fraction(1, 4)))

    def test_v1_and_pair_reports_coexist_and_keep_separate_readers(self):
        designs = shared_inputs(self.station, self.station)
        pair_receipt = receive(self.center, *issue_pair(self.station, designs['old'], designs['new']))
        other_receipt = receive(self.center, *issue(self.station, designs['other']))
        pair_report = publish_pair(self.center, pair_receipt, other_receipt, 1)
        # V1 publish needs two V1 receipts.
        v1_a = receive(self.center, *issue(self.station, designs['old']))
        legacy_report = publish(self.center, v1_a, other_receipt, 1)
        self.assertIsNone(read(self.center, pair_report.record.report_id))
        self.assertIsNone(read_pair(self.center, legacy_report.record.report_id))
        self.assertEqual(read_pair(self.center, pair_report.record.report_id), pair_report)
        self.assertEqual(read(self.center, legacy_report.record.report_id), legacy_report)
