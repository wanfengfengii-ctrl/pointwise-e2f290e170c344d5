import sqlite3

from exchange.catalog import _decode, _digest_for, load_by_issue, store_receipt
from ledger import InvalidInput, require_key, transaction


def receive(db: sqlite3.Connection, issue_id: str, wire: bytes) -> int:
    issue_id = require_key(issue_id, 'issue_id')
    packet = _decode(wire)
    if issue_id != packet.issue_id:
        raise InvalidInput('the delivered issue ID differs from the packet issue ID')
    digest = _digest_for(packet)
    with transaction(db):
        existing = load_by_issue(db, issue_id)
        if existing is None:
            receipt_id = store_receipt(db, packet, wire)
        else:
            if existing.wire != wire or existing.digest != digest:
                raise InvalidInput('a different packet already uses this issue ID')
            receipt_id = existing.receipt_id
    return receipt_id
