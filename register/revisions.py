from collections.abc import Mapping
from dataclasses import dataclass
import sqlite3

from ledger import InvalidInput, UnknownRecord, require_id, transaction
from register.observations import Observation, load_observations, validate_reading, write_observations
from register.shifts import register_shift
from register.specimens import bind_specimen


@dataclass(frozen=True)
class ReadingRevision:
    revision_id: int
    shift_id: str
    previous_revision_id: int | None
    observations: tuple[Observation, ...]


def revise(
    db: sqlite3.Connection,
    shift_id: str,
    changes: Mapping[str, tuple[str | None, int]],
) -> int:
    if not isinstance(changes, Mapping) or not changes:
        raise InvalidInput('changes must be a nonempty reading map')
    with transaction(db, allow_nested=True):
        register_shift(db, shift_id)
        current = db.execute(
            'SELECT revision_id FROM reading_revisions WHERE shift_id = ? '
            'ORDER BY revision_id DESC LIMIT 1',
            (shift_id,),
        ).fetchone()
        previous_id = current[0] if current is not None else None
        snapshot = {}
        if previous_id is not None:
            snapshot = {
                row.specimen.local_id: row for row in load_observations(db, previous_id)
            }
        for local_id, change in changes.items():
            if not isinstance(change, (tuple, list)) or len(change) != 2:
                raise InvalidInput('each change needs a shared registration and a reading')
            registration, value = change
            reading = validate_reading(value)
            specimen = bind_specimen(db, shift_id, local_id, registration)
            snapshot[local_id] = Observation(specimen, reading)
        cursor = db.execute(
            'INSERT INTO reading_revisions(shift_id, previous_revision_id) VALUES (?, ?)',
            (shift_id, previous_id),
        )
        revision_id = cursor.lastrowid
        write_observations(db, revision_id, snapshot.values())
    return revision_id


def load_revision(db: sqlite3.Connection, revision_id: int) -> ReadingRevision:
    revision_id = require_id(revision_id, 'revision_id')
    row = db.execute(
        'SELECT shift_id, previous_revision_id FROM reading_revisions WHERE revision_id = ?',
        (revision_id,),
    ).fetchone()
    if row is None:
        raise UnknownRecord(f'unknown revision {revision_id}')
    return ReadingRevision(revision_id, *row, load_observations(db, revision_id))
