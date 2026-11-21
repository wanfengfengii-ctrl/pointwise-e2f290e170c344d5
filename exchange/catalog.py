from dataclasses import dataclass
import sqlite3

from exchange.codec import BatchPacket, decode_packet, packet_digest
from ledger import require_id, require_key


@dataclass(frozen=True)
class ReceivedBatch:
    receipt_id: int
    packet: BatchPacket
    wire: bytes
    digest: str


def _received(row) -> ReceivedBatch | None:
    if row is None:
        return None
    receipt_id, wire, digest = row
    return ReceivedBatch(receipt_id, decode_packet(wire), wire, digest)


def load_receipt(db: sqlite3.Connection, receipt_id: int) -> ReceivedBatch | None:
    receipt_id = require_id(receipt_id, 'receipt_id')
    row = db.execute(
        'SELECT receipt_id, wire, digest FROM intake WHERE receipt_id = ?', (receipt_id,)
    ).fetchone()
    return _received(row)


def load_by_issue(db: sqlite3.Connection, issue_id: str) -> ReceivedBatch | None:
    issue_id = require_key(issue_id, 'issue_id')
    row = db.execute(
        'SELECT receipt_id, wire, digest FROM intake WHERE issue_id = ?', (issue_id,)
    ).fetchone()
    return _received(row)


def store_receipt(db: sqlite3.Connection, packet: BatchPacket, wire: bytes) -> int:
    cursor = db.execute(
        'INSERT INTO intake(issue_id, wire, digest) VALUES (?, ?, ?)',
        (packet.issue_id, wire, packet_digest(packet)),
    )
    return cursor.lastrowid
