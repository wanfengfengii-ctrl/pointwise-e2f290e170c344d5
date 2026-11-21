from fractions import Fraction
import sqlite3

from analysis.risk import publish
from exchange.catalog import load_receipt
from exchange.intake import receive
from ledger import InvalidInput, UnknownRecord, init_center, init_station
from register.revisions import load_revision, revise
from report.retrieve import read
from samples.demo import load_sample, load_scenario
from sampling.design import freeze
from tests.fixtures import LedgerFixture, REPORT_TABLES, STATION_TABLES, counts


class TestPublication(LedgerFixture):
    def test_missing_parent(self):
        left, _ = self.main_pair()
        self.detach()
        before = counts(self.center, *REPORT_TABLES)
        with self.assertRaises(UnknownRecord):
            publish(self.center, left, 999, 2)
        self.assertEqual(counts(self.center, *REPORT_TABLES), before)

    def test_invalid_request(self):
        left, right = self.main_pair()
        second_for_left = self.ship(load_receipt(self.center, left).packet.design_id)
        self.detach()
        before = counts(self.center, *REPORT_TABLES)
        for args in ((left, second_for_left, 2), (left, right), (left, right, True), (left, right, -1)):
            with self.subTest(args=args), self.assertRaises(InvalidInput):
                publish(self.center, *args)
            self.assertEqual(counts(self.center, *REPORT_TABLES), before)

    def test_failed_write(self):
        left, right = self.main_pair()
        self.detach()
        original = publish(self.center, left, right, 2)
        before = counts(self.center, *REPORT_TABLES)
        self.center.execute(
            "CREATE TRIGGER reject_receipt BEFORE INSERT ON report_receipts "
            "BEGIN SELECT RAISE(ABORT, 'receipt ledger is closed'); END"
        )
        with self.assertRaisesRegex(sqlite3.IntegrityError, 'receipt ledger is closed'):
            publish(self.center, left, right, 1)
        self.reopen_center()
        self.assertEqual(counts(self.center, *REPORT_TABLES), before)
        self.assertEqual(read(self.center, original.record.report_id), original)
        self.center.execute('DROP TRIGGER reject_receipt')
        retry = publish(self.center, left, right, 1)
        self.assertEqual(retry.record.zero_probability, Fraction(0))
        self.assertEqual(counts(self.center, *REPORT_TABLES), {'reports': 2, 'report_parents': 4, 'report_receipts': 2})

    def test_reopen_original(self):
        left, right = self.main_pair()
        original = publish(self.center, left, right, 2)
        revise(self.station, '甲班', {'A-x': ('x', 0)})
        self.detach()
        self.reopen_center()
        archived = read(self.center, original.record.report_id)
        self.assertEqual(archived, original)
        self.assertEqual(archived.record.zero_probability, Fraction(1, 3))
        self.assertEqual(tuple(parent.receipt_id for parent in archived.parents), (left, right))

    def test_original_parent_after_new_report(self):
        left, right = self.main_pair()
        original = publish(self.center, left, right, 2)
        changed_revision = revise(self.station, '甲班', {'A-x': ('x', 0)})
        new_design = freeze(self.station, '甲班', changed_revision, 'v1', {'rack': ('A-x', 'A-a')}, {'rack': 1})
        new_left = self.ship(new_design)
        self.detach()
        newer = publish(self.center, right, new_left, 2)
        self.assertEqual(newer.record.condition_mass, Fraction(3, 4))
        self.assertEqual(newer.record.zero_probability, Fraction(2, 3))
        self.assertEqual(tuple(parent.receipt_id for parent in newer.parents), (right, new_left))
        self.assertNotEqual(newer.parents[1].issue_id, original.parents[0].issue_id)
        self.assertEqual(newer.parents[1].revision_id, changed_revision)
        self.reopen_center()
        archived = read(self.center, original.record.report_id)
        self.assertEqual(archived, original)
        self.assertEqual(archived.record.zero_probability, Fraction(1, 3))
        self.assertEqual(tuple(parent.receipt_id for parent in archived.parents), (left, right))
        self.assertEqual(read(self.center, newer.record.report_id), newer)

    def test_unknown_report(self):
        before = counts(self.center, *REPORT_TABLES)
        self.assertIsNone(read(self.center, 1))
        self.assertEqual(counts(self.center, *REPORT_TABLES), before)

    def test_repeat_init(self):
        scenario = load_scenario()
        shipments = load_sample(self.station, scenario)
        receipts = tuple(receive(self.center, *shipment) for shipment in shipments)
        original = publish(self.center, *receipts, 2)
        changed = revise(self.station, '甲班', {'A-x': ('x', 0)})
        corrected = load_revision(self.station, changed)
        pinned_revision = original.parents[0].revision_id
        old_snapshot = load_revision(self.station, pinned_revision)
        station_before = counts(self.station, *STATION_TABLES)
        center_before = counts(self.center, 'intake', *REPORT_TABLES)
        init_station(self.station)
        init_center(self.center)
        self.assertEqual(load_sample(self.station, scenario), shipments)
        self.assertEqual(tuple(receive(self.center, *shipment) for shipment in shipments), receipts)
        self.assertEqual(load_revision(self.station, changed), corrected)
        self.assertEqual(load_revision(self.station, pinned_revision), old_snapshot)
        self.assertEqual([row.microns for row in corrected.observations], [0, 0])
        self.assertEqual([row.microns for row in old_snapshot.observations], [0, 12])
        self.assertEqual(read(self.center, original.record.report_id), original)
        self.assertEqual(counts(self.station, *STATION_TABLES), station_before)
        self.assertEqual(counts(self.center, 'intake', *REPORT_TABLES), center_before)
