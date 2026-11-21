from dataclasses import dataclass
import sqlite3

from ledger import InvalidInput, UnknownRecord, require_key
from register.shared import resolve_shared
from register.shifts import get_shift


@dataclass(frozen=True)
class SpecimenRef:
    specimen_id: int
    shift_id: str
    local_id: str
    shared_key: str | None

    @property
    def physical_key(self) -> tuple[str, str | int]:
        if self.shared_key is not None:
            return ('shared', self.shared_key)
        return ('private', self.specimen_id)


def get_specimen(db: sqlite3.Connection, shift_id: str, local_id: str) -> SpecimenRef | None:
    shift_id = require_key(shift_id, 'shift_id')
    local_id = require_key(local_id, 'local_id')
    row = db.execute(
        'SELECT specimen_id, shift_id, local_id, shared_key FROM specimens '
        'WHERE shift_id = ? AND local_id = ?',
        (shift_id, local_id),
    ).fetchone()
    return SpecimenRef(*row) if row is not None else None


def bind_specimen(
    db: sqlite3.Connection, shift_id: str, local_id: str, registration: str | None
) -> SpecimenRef:
    if get_shift(db, shift_id) is None:
        raise UnknownRecord(f'unknown shift {shift_id!r}')
    current = get_specimen(db, shift_id, local_id)
    shared_key = None if registration is None else resolve_shared(db, registration).key
    if current is not None:
        if current.shared_key != shared_key:
            raise InvalidInput(f'conflicting physical binding for {shift_id!r}/{local_id!r}')
        return current
    cursor = db.execute(
        'INSERT INTO specimens(shift_id, local_id, shared_key) VALUES (?, ?, ?)',
        (shift_id, local_id, shared_key),
    )
    return SpecimenRef(cursor.lastrowid, shift_id, local_id, shared_key)
