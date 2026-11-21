from dataclasses import dataclass
import sqlite3

from ledger import require_key


@dataclass(frozen=True)
class Shift:
    shift_id: str


def register_shift(db: sqlite3.Connection, shift_id: str) -> Shift:
    shift_id = require_key(shift_id, 'shift_id')
    db.execute('INSERT INTO shifts(shift_id) VALUES (?) ON CONFLICT(shift_id) DO NOTHING', (shift_id,))
    return Shift(shift_id)


def get_shift(db: sqlite3.Connection, shift_id: str) -> Shift | None:
    shift_id = require_key(shift_id, 'shift_id')
    row = db.execute('SELECT shift_id FROM shifts WHERE shift_id = ?', (shift_id,)).fetchone()
    return Shift(*row) if row is not None else None
