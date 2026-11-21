"""Resolve and validate a paired-review publication request."""
import sqlite3

from exchange.catalog import ReceivedBatch, load_receipt
from exchange.codec import BatchPacket
from exchange.paired_codec import PairedPacket
from ledger import InvalidInput, UnknownRecord


def resolve_pair_request(
    db: sqlite3.Connection, pair_receipt_id: int, other_receipt_id: int
) -> tuple[ReceivedBatch, ReceivedBatch]:
    paired = load_receipt(db, pair_receipt_id)
    other = load_receipt(db, other_receipt_id)
    if paired is None:
        raise UnknownRecord(f'unknown receipt {pair_receipt_id}')
    if other is None:
        raise UnknownRecord(f'unknown receipt {other_receipt_id}')
    if not isinstance(paired.packet, PairedPacket):
        raise InvalidInput('the first parent must be a version-2 paired batch')
    if not isinstance(other.packet, BatchPacket):
        raise InvalidInput('the second parent must be a version-1 single-version batch')
    if paired.packet.shift_id == other.packet.shift_id:
        raise InvalidInput('a paired review requires receipts from two different shifts')
    return paired, other
