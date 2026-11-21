from dataclasses import dataclass
import sqlite3

from ledger import InvalidInput, UnknownRecord, require_key, transaction
from register.observations import validate_reading
from register.shifts import register_shift


@dataclass(frozen=True)
class ProtocolVersion:
    shift_id: str
    version: str
    threshold_microns: int


def register_protocol(
    db: sqlite3.Connection, shift_id: str, version: str, threshold: int
) -> ProtocolVersion:
    version = require_key(version, 'protocol version')
    threshold = validate_reading(threshold)
    with transaction(db, allow_nested=True):
        register_shift(db, shift_id)
        db.execute(
            'INSERT INTO protocols(shift_id, version, threshold_hex) VALUES (?, ?, ?) '
            'ON CONFLICT(shift_id, version) DO NOTHING',
            (shift_id, version, format(threshold, 'x')),
        )
        protocol = load_protocol(db, shift_id, version)
        if protocol.threshold_microns != threshold:
            raise InvalidInput('a registered protocol version has an immutable threshold')
    return protocol


def load_protocol(db: sqlite3.Connection, shift_id: str, version: str) -> ProtocolVersion:
    shift_id = require_key(shift_id, 'shift_id')
    version = require_key(version, 'protocol version')
    row = db.execute(
        'SELECT threshold_hex FROM protocols WHERE shift_id = ? AND version = ?',
        (shift_id, version),
    ).fetchone()
    if row is None:
        raise UnknownRecord(f'unknown protocol {version!r} for shift {shift_id!r}')
    return ProtocolVersion(shift_id, version, int(row[0], 16))
