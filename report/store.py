from dataclasses import dataclass
from fractions import Fraction
import sqlite3

from ledger import InvalidInput, require_id


@dataclass(frozen=True)
class ReportRecord:
    report_id: int
    m: int
    status: str
    condition_mass: Fraction
    zero_probability: Fraction | None


def _fraction_parts(value: Fraction) -> tuple[str, str]:
    return format(value.numerator, 'x'), format(value.denominator, 'x')


def insert_report(
    db: sqlite3.Connection,
    m: int,
    status: str,
    condition_mass: Fraction,
    zero_probability: Fraction | None,
) -> ReportRecord:
    if type(m) is not int or m < 0 or not isinstance(condition_mass, Fraction):
        raise InvalidInput('invalid distinct count or condition mass for publication')
    if status == 'reachable':
        if not 0 < condition_mass <= 1 or not isinstance(zero_probability, Fraction) or not 0 <= zero_probability <= 1:
            raise InvalidInput('a reachable report needs positive condition mass and a valid probability')
    elif status != 'unreachable' or condition_mass != 0 or zero_probability is not None:
        raise InvalidInput('an unreachable report needs zero condition mass and an empty probability')
    mass_parts = _fraction_parts(condition_mass)
    probability_parts = (None, None) if zero_probability is None else _fraction_parts(zero_probability)
    cursor = db.execute(
        'INSERT INTO reports(m_hex, status, mass_numerator, mass_denominator, '
        'probability_numerator, probability_denominator) VALUES (?, ?, ?, ?, ?, ?)',
        (format(m, 'x'), status, *mass_parts, *probability_parts),
    )
    return ReportRecord(cursor.lastrowid, m, status, condition_mass, zero_probability)


def load_report(db: sqlite3.Connection, report_id: int) -> ReportRecord | None:
    report_id = require_id(report_id, 'report_id')
    row = db.execute(
        'SELECT m_hex, status, mass_numerator, mass_denominator, probability_numerator, '
        'probability_denominator FROM reports WHERE report_id = ?',
        (report_id,),
    ).fetchone()
    if row is None:
        return None
    m, status, mass_n, mass_d, probability_n, probability_d = row
    mass = Fraction(int(mass_n, 16), int(mass_d, 16))
    probability = None if probability_n is None else Fraction(int(probability_n, 16), int(probability_d, 16))
    return ReportRecord(report_id, int(m, 16), status, mass, probability)
