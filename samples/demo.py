from contextlib import closing
from dataclasses import asdict
import json
from pathlib import Path
from tempfile import TemporaryDirectory

from analysis.risk import publish
from exchange.intake import receive
from exchange.issue import issue
from ledger import open_center, open_station, transaction
from register.revisions import revise
from report.retrieve import read
from sampling.design import freeze
from sampling.protocols import register_protocol


def load_scenario() -> dict:
    return json.loads(Path(__file__).with_name('two_shifts.json').read_text(encoding='utf-8'))


def load_sample(db, scenario: dict, position: int | None = None) -> tuple[tuple[str, bytes], ...]:
    key = scenario['sample_key']
    selected = range(len(scenario['shifts'])) if position is None else (position,)
    shipments = []
    with transaction(db):
        for index in selected:
            row = db.execute(
                'SELECT i.issue_id, i.wire FROM sample_issues AS s JOIN issued_batches AS i USING (issue_id) '
                'WHERE s.sample_key = ? AND s.position = ?',
                (key, index),
            ).fetchone()
            if row is None:
                sample = scenario['shifts'][index]
                shift_id = sample['shift_id']
                version = sample['version']
                revision = revise(db, shift_id, sample['readings'])
                register_protocol(db, shift_id, version, sample['threshold'])
                design = freeze(db, shift_id, revision, version, sample['layers'], sample['quotas'])
                row = issue(db, design)
                db.execute(
                    'INSERT INTO sample_issues(sample_key, position, issue_id) VALUES (?, ?, ?)',
                    (key, index, row[0]),
                )
            shipments.append(row)
    return tuple(shipments)


def _ratio(value):
    return None if value is None else f'{value.numerator}/{value.denominator}'


def main() -> None:
    scenario = load_scenario()
    with TemporaryDirectory(prefix='thin-plate-demo-') as directory:
        root = Path(directory)
        left_path = root / 'shift-a.sqlite'
        right_path = root / 'shift-b.sqlite'
        center_path = root / 'center.sqlite'
        with (
            closing(open_station(left_path)) as left_station,
            closing(open_station(right_path)) as right_station,
            closing(open_center(center_path)) as center,
        ):
            left_wire, = load_sample(left_station, scenario, 0)
            right_wire, = load_sample(right_station, scenario, 1)
            left = receive(center, *left_wire)
            right = receive(center, *right_wire)
        left_path.unlink()
        right_path.unlink()

        with closing(open_center(center_path)) as center:
            signed = [publish(center, left, right, m) for m in scenario['distinct_totals']]
        with closing(open_center(center_path)) as center:
            for original in signed:
                archived = read(center, original.record.report_id)
                if archived != original:
                    raise RuntimeError(f'archived report {original.record.report_id} changed')
                record = archived.record
                print(json.dumps({
                    'report_id': record.report_id,
                    'm': record.m,
                    'status': record.status,
                    'condition_mass': _ratio(record.condition_mass),
                    'zero_probability': _ratio(record.zero_probability),
                    'parents': [asdict(parent) for parent in archived.parents],
                    'receipt': asdict(archived.receipt),
                }, ensure_ascii=False, sort_keys=True))


if __name__ == '__main__':
    main()
