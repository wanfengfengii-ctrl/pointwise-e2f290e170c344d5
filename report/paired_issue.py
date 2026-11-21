"""Issue and read back paired-review reports."""
from dataclasses import dataclass
import sqlite3

from exchange.catalog import ReceivedBatch
from ledger import transaction
from report.paired_provenance import (
    PairParentReference,
    capture_pair_parents,
    read_pair_parents,
    store_pair_parents,
)
from report.paired_store import PairReportRecord, insert_pair_report, load_pair_report
from report.receipt import ReportReceipt, create_report_receipt, load_report_receipt


@dataclass(frozen=True)
class PairedPublishedReport:
    record: PairReportRecord
    parents: tuple[PairParentReference, PairParentReference]
    receipt: ReportReceipt


def issue_pair_report(
    db: sqlite3.Connection,
    m: int,
    status: str,
    condition_mass,
    probabilities,
    paired: ReceivedBatch,
    other: ReceivedBatch,
) -> PairedPublishedReport:
    with transaction(db):
        record = insert_pair_report(db, m, status, condition_mass, probabilities)
        parents = capture_pair_parents(paired, other)
        store_pair_parents(db, record.report_id, parents)
        receipt = create_report_receipt(db, record.report_id)
    return PairedPublishedReport(record, parents, receipt)
