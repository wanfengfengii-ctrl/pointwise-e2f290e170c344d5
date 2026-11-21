from dataclasses import dataclass
from fractions import Fraction
import sqlite3

from exchange.catalog import ReceivedBatch
from ledger import transaction
from report.provenance import ParentReference, capture_parents, store_parents
from report.receipt import ReportReceipt, create_report_receipt
from report.store import ReportRecord, insert_report


@dataclass(frozen=True)
class PublishedReport:
    record: ReportRecord
    parents: tuple[ParentReference, ParentReference]
    receipt: ReportReceipt


def issue_report(
    db: sqlite3.Connection,
    m: int,
    status: str,
    condition_mass: Fraction,
    zero_probability: Fraction | None,
    left: ReceivedBatch,
    right: ReceivedBatch,
) -> PublishedReport:
    with transaction(db):
        record = insert_report(db, m, status, condition_mass, zero_probability)
        parents = capture_parents(left, right)
        store_parents(db, record.report_id, parents)
        receipt = create_report_receipt(db, record.report_id)
    return PublishedReport(record, parents, receipt)
