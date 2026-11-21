from dataclasses import dataclass
import sqlite3
from uuid import NAMESPACE_URL, uuid5

from ledger import require_key


@dataclass(frozen=True)
class SharedSpecimen:
    key: str
    registration: str


def resolve_shared(db: sqlite3.Connection, registration: str) -> SharedSpecimen:
    registration = require_key(registration, 'shared registration')
    key = uuid5(NAMESPACE_URL, 'urn:thin-plate:shared-specimen:' + registration).hex
    db.execute(
        'INSERT INTO shared_specimens(shared_key, registration) VALUES (?, ?) '
        'ON CONFLICT(registration) DO NOTHING',
        (key, registration),
    )
    row = db.execute(
        'SELECT shared_key, registration FROM shared_specimens WHERE registration = ?',
        (registration,),
    ).fetchone()
    return SharedSpecimen(*row)


def get_shared(db: sqlite3.Connection, key: str) -> SharedSpecimen | None:
    key = require_key(key, 'shared key')
    row = db.execute(
        'SELECT shared_key, registration FROM shared_specimens WHERE shared_key = ?', (key,)
    ).fetchone()
    return SharedSpecimen(*row) if row is not None else None
