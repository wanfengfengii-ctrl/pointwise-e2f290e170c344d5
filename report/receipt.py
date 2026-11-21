from dataclasses import dataclass
import sqlite3
from uuid import uuid4


@dataclass(frozen=True)
class ReportReceipt:
    report_id: int
    token: str


def create_report_receipt(db: sqlite3.Connection, report_id: int) -> ReportReceipt:
    token = uuid4().hex
    db.execute('INSERT INTO report_receipts(report_id, token) VALUES (?, ?)', (report_id, token))
    return ReportReceipt(report_id, token)


def load_report_receipt(db: sqlite3.Connection, report_id: int) -> ReportReceipt:
    row = db.execute('SELECT token FROM report_receipts WHERE report_id = ?', (report_id,)).fetchone()
    if row is None:
        raise sqlite3.IntegrityError(f'report {report_id} has no committed receipt')
    return ReportReceipt(report_id, row[0])
