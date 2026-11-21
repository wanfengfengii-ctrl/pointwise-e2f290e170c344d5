from dataclasses import dataclass
import sqlite3

from exchange.catalog import ReceivedBatch, load_receipt
from exchange.codec import BatchPacket
from ledger import InvalidInput, UnknownRecord


@dataclass(frozen=True)
class RiskRequest:
    left_receipt: int
    right_receipt: int
    m: int | None = None


def validate_distinct_total(m: object) -> int:
    if type(m) is not int or m < 0:
        raise InvalidInput('m must be a nonnegative integer distinct specimen count')
    return m


def resolve_request(db: sqlite3.Connection, request: RiskRequest) -> tuple[ReceivedBatch, ReceivedBatch]:
    validate_distinct_total(request.m)
    left = load_receipt(db, request.left_receipt)
    right = load_receipt(db, request.right_receipt)
    if left is None:
        raise UnknownRecord(f'unknown receipt {request.left_receipt}')
    if right is None:
        raise UnknownRecord(f'unknown receipt {request.right_receipt}')
    if not isinstance(left.packet, BatchPacket) or not isinstance(right.packet, BatchPacket):
        raise InvalidInput('the version-1 review requires two version-1 single-version batches')
    if left.packet.shift_id == right.packet.shift_id:
        raise InvalidInput('a review requires receipts from two different shifts')
    return left, right
