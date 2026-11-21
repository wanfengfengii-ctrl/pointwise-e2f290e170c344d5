"""End-to-end paired-review demo.

Two station databases issue a version-2 paired batch and a version-1 batch.
The station databases are closed and removed before the center signs the
paired report; reopening the center later lets the next shift retrieve the
exact four cells, the three frozen designs and the receipt by report number.
"""
from contextlib import closing
from dataclasses import asdict
import json
from pathlib import Path
from tempfile import TemporaryDirectory

from analysis.risk import publish_pair
from exchange.intake import receive
from exchange.issue import issue
from exchange.paired_issue import issue_pair
from ledger import InvalidInput, open_center, open_station
from report.paired_retrieve import read_pair
from samples.paired_inputs import private_inputs, shared_inputs


def _ratio(value):
    return f'{value.numerator}/{value.denominator}'


def _pair_shipments(builder, root: Path):
    station_path = root / 'shift-a.sqlite'
    other_path = root / 'shift-b.sqlite'
    with (
        closing(open_station(station_path)) as station,
        closing(open_station(other_path)) as other_station,
    ):
        designs = builder(station, other_station)
        names = [name for name in designs if name != 'other']
        paired = {
            name: issue_pair(station, designs['old'], designs[name])
            for name in names if name != 'old' and name != 'replaced'
        }
        if 'replaced' in designs:
            try:
                issue_pair(station, designs['old'], designs['replaced'])
            except InvalidInput as error:
                print(f'拒绝同层换片配对: {error}')
        other_shipment = issue(other_station, designs['other'])
    return paired, other_shipment, station_path, other_path


def _print_report(signed):
    record = signed.record
    payload = {
        'report_id': record.report_id,
        'm': record.m,
        'status': record.status,
        'condition_mass': _ratio(record.condition_mass),
        'probabilities': None if record.probabilities is None
        else [_ratio(value) for value in record.probabilities],
        'parents': [
            {
                'receipt_id': parent.receipt_id,
                'issue_id': parent.issue_id,
                'shift_id': parent.shift_id,
                'digest': parent.digest,
                'designs': [asdict(design) for design in parent.designs],
            }
            for parent in signed.parents
        ],
        'receipt': asdict(signed.receipt),
    }
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True))


def main() -> None:
    with TemporaryDirectory(prefix='thin-plate-paired-demo-') as directory:
        root = Path(directory)
        center_path = root / 'center.sqlite'

        # Private-scenario stations: kept grades and swapped grades.
        paired_shipments, other_shipment, station_path, other_path = _pair_shipments(
            private_inputs, root
        )
        with closing(open_center(center_path)) as center:
            other_receipt = receive(center, *other_shipment)
            pair_receipts = {
                name: receive(center, *shipment)
                for name, shipment in paired_shipments.items()
            }
            # Replay the exact canonical piece: the receipt number is reused.
            replay = receive(center, *paired_shipments['kept'])
            assert replay == pair_receipts['kept']
        # Stations are closed and the station files removed.
        station_path.unlink()
        other_path.unlink()

        with closing(open_center(center_path)) as center:
            signed = {
                name: publish_pair(center, receipt, other_receipt, 2)
                for name, receipt in pair_receipts.items()
            }

        # The next shift reopens the center and retrieves everything by number.
        with closing(open_center(center_path)) as center:
            for name, original in signed.items():
                archived = read_pair(center, original.record.report_id)
                if archived != original:
                    raise RuntimeError(f'archived paired report {name!r} changed after reopening')
                print(f'私件场景 {name}:')
                _print_report(archived)

        # Shared-scenario station demonstrates the deduped conditional table.
        shared_paired, shared_other, shared_station, shared_other_station = _pair_shipments(
            shared_inputs, root
        )
        shared_station.unlink()
        shared_other_station.unlink()
        with closing(open_center(center_path)) as center:
            shared_pair_receipt = receive(center, *shared_paired['new'])
            shared_other_receipt = receive(center, *shared_other)
            shared_reports = [
                publish_pair(center, shared_pair_receipt, shared_other_receipt, m)
                for m in (1, 2, 3)
            ]
        with closing(open_center(center_path)) as center:
            for original in shared_reports:
                archived = read_pair(center, original.record.report_id)
                if archived != original:
                    raise RuntimeError('archived shared paired report changed after reopening')
                print(f'共享场景 m={original.record.m}:')
                _print_report(archived)


if __name__ == '__main__':
    main()
