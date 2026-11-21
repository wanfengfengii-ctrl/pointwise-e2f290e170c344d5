"""Read back finalized paired-review reports by report number."""
import sqlite3

from report.paired_issue import PairedPublishedReport
from report.paired_provenance import read_pair_parents
from report.paired_store import load_pair_report
from report.receipt import load_report_receipt


def read_pair(db: sqlite3.Connection, report_id: int) -> PairedPublishedReport | None:
    record = load_pair_report(db, report_id)
    if record is None:
        return None
    parents = read_pair_parents(db, report_id)
    receipt = load_report_receipt(db, report_id)
    return PairedPublishedReport(record, parents, receipt)
