from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from exchange.intake import receive
from exchange.issue import issue
from ledger import open_center, open_station
from register.revisions import revise
from sampling.design import freeze
from sampling.protocols import register_protocol


REPORT_TABLES = ('reports', 'report_parents', 'report_receipts')
STATION_TABLES = (
    'shifts', 'shared_specimens', 'specimens', 'reading_revisions', 'observations',
    'protocols', 'designs', 'design_layers', 'frame_members', 'issued_batches', 'sample_issues',
)


def counts(db, *tables: str) -> dict[str, int]:
    return {table: db.execute(f'SELECT count(*) FROM {table}').fetchone()[0] for table in tables}


class LedgerFixture(unittest.TestCase):
    def setUp(self):
        directory = TemporaryDirectory(prefix='thin-plate-test-')
        self.addCleanup(directory.cleanup)
        root = Path(directory.name)
        self.station_path = root / 'station.sqlite'
        self.center_path = root / 'center.sqlite'
        self.station = open_station(self.station_path)
        self.addCleanup(self.close_station)
        self.center = open_center(self.center_path)
        self.addCleanup(self.close_center)

    def close_station(self):
        if self.station is not None:
            self.station.close()
            self.station = None

    def close_center(self):
        if self.center is not None:
            self.center.close()
            self.center = None

    def detach(self):
        self.close_station()
        self.station_path.unlink()

    def reopen_center(self):
        self.close_center()
        self.center = open_center(self.center_path)

    def design(self, shift_id, readings, layers, quotas, threshold=10, version='v1'):
        revision = revise(self.station, shift_id, readings)
        register_protocol(self.station, shift_id, version, threshold)
        return freeze(self.station, shift_id, revision, version, layers, quotas)

    def ship(self, design_id):
        return receive(self.center, *issue(self.station, design_id))

    def main_pair(self, right_shared='x'):
        left = self.design(
            '甲班', {'A-x': ('x', 12), 'A-a': (None, 0)},
            {'rack': ('A-x', 'A-a')}, {'rack': 1},
        )
        right = self.design(
            '乙班', {'B-x': (right_shared, 10), 'B-b': (None, -3)},
            {'rack': ('B-x', 'B-b')}, {'rack': 1},
        )
        return self.ship(left), self.ship(right)
