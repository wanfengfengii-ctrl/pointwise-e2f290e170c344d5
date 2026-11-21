from dataclasses import dataclass
import sqlite3

from exchange.catalog import ReceivedBatch, load_receipt


@dataclass(frozen=True)
class ParentReference:
    receipt_id: int
    issue_id: str
    shift_id: str
    design_id: int
    revision_id: int
    protocol_version: str
    digest: str


def _reference(batch: ReceivedBatch) -> ParentReference:
    packet = batch.packet
    return ParentReference(
        batch.receipt_id, packet.issue_id, packet.shift_id, packet.design_id,
        packet.revision_id, packet.protocol_version, batch.digest,
    )


def capture_parents(left: ReceivedBatch, right: ReceivedBatch) -> tuple[ParentReference, ParentReference]:
    return _reference(left), _reference(right)


def store_parents(
    db: sqlite3.Connection, report_id: int, parents: tuple[ParentReference, ParentReference]
) -> None:
    db.executemany(
        'INSERT INTO report_parents(report_id, position, receipt_id, digest) VALUES (?, ?, ?, ?)',
        ((report_id, index, parent.receipt_id, parent.digest) for index, parent in enumerate(parents)),
    )


def read_report_parents(db: sqlite3.Connection, report_id: int) -> tuple[ParentReference, ParentReference]:
    rows = db.execute(
        'SELECT position, receipt_id, digest FROM report_parents WHERE report_id = ? ORDER BY position',
        (report_id,),
    ).fetchall()
    if [row[0] for row in rows] != [0, 1]:
        raise sqlite3.IntegrityError(f'report {report_id} does not have two ordered parents')
    parents = []
    for _, receipt_id, digest in rows:
        batch = load_receipt(db, receipt_id)
        if batch is None or batch.digest != digest:
            raise sqlite3.IntegrityError(f'report {report_id} has an inconsistent parent {receipt_id}')
        parents.append(batch)
    return capture_parents(*parents)
