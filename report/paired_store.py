"""Persistence of paired-review report records."""
from dataclasses import dataclass
from fractions import Fraction
import sqlite3

from ledger import InvalidInput, require_id


@dataclass(frozen=True)
class PairReportRecord:
    report_id: int
    m: int
    status: str
    condition_mass: Fraction
    probabilities: tuple[Fraction, Fraction, Fraction, Fraction] | None


def _fraction_parts(value: Fraction) -> tuple[str, str]:
    return format(value.numerator, 'x'), format(value.denominator, 'x')


def insert_pair_report(
    db: sqlite3.Connection,
    m: int,
    status: str,
    condition_mass: Fraction,
    probabilities: tuple[Fraction, Fraction, Fraction, Fraction] | None,
) -> PairReportRecord:
    if type(m) is not int or m < 0 or not isinstance(condition_mass, Fraction):
        raise InvalidInput('invalid distinct count or condition mass for paired publication')
    if status == 'reachable':
        if (
            condition_mass <= 0
            or not isinstance(probabilities, tuple)
            or len(probabilities) != 4
            or not all(isinstance(value, Fraction) and 0 <= value <= 1 for value in probabilities)
        ):
            raise InvalidInput('a reachable paired report needs four exact cell probabilities')
    elif status != 'unreachable' or condition_mass != 0 or probabilities is not None:
        raise InvalidInput('an unreachable paired report needs zero mass and empty cells')
    cursor = db.execute(
        'INSERT INTO reports(kind, m_hex, status, mass_numerator, mass_denominator, '
        'probability_numerator, probability_denominator) VALUES (?, ?, ?, ?, ?, NULL, NULL)',
        ('pair', format(m, 'x'), status, *_fraction_parts(condition_mass)),
    )
    report_id = cursor.lastrowid
    if probabilities is not None:
        db.executemany(
            'INSERT INTO pair_report_cells(report_id, position, numerator, denominator) '
            'VALUES (?, ?, ?, ?)',
            (
                (report_id, position, *_fraction_parts(value))
                for position, value in enumerate(probabilities)
            ),
        )
    return PairReportRecord(report_id, m, status, condition_mass, probabilities)


def load_pair_report(db: sqlite3.Connection, report_id: int) -> PairReportRecord | None:
    report_id = require_id(report_id, 'report_id')
    row = db.execute(
        'SELECT kind, m_hex, status, mass_numerator, mass_denominator FROM reports '
        'WHERE report_id = ?',
        (report_id,),
    ).fetchone()
    if row is None or row[0] != 'pair':
        return None
    _, m_hex, status, mass_n, mass_d = row
    mass = Fraction(int(mass_n, 16), int(mass_d, 16))
    cell_rows = db.execute(
        'SELECT position, numerator, denominator FROM pair_report_cells '
        'WHERE report_id = ? ORDER BY position',
        (report_id,),
    ).fetchall()
    probabilities = None
    if cell_rows:
        if [cell[0] for cell in cell_rows] != [0, 1, 2, 3]:
            raise sqlite3.IntegrityError(f'paired report {report_id} does not have four cells')
        probabilities = tuple(
            Fraction(int(numerator, 16), int(denominator, 16))
            for _, numerator, denominator in cell_rows
        )
    return PairReportRecord(report_id, int(m_hex, 16), status, mass, probabilities)
