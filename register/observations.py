from collections.abc import Iterable
from dataclasses import dataclass
import sqlite3

from ledger import InvalidInput
from register.specimens import SpecimenRef


@dataclass(frozen=True)
class Observation:
    specimen: SpecimenRef
    microns: int


def validate_reading(value: object) -> int:
    if type(value) is not int:
        raise InvalidInput('reading must be an integer number of microns')
    return value


def write_observations(
    db: sqlite3.Connection, revision_id: int, observations: Iterable[Observation]
) -> None:
    db.executemany(
        'INSERT INTO observations(revision_id, specimen_id, microns_hex) VALUES (?, ?, ?)',
        (
            (revision_id, observation.specimen.specimen_id, format(observation.microns, 'x'))
            for observation in observations
        ),
    )


def load_observations(db: sqlite3.Connection, revision_id: int) -> tuple[Observation, ...]:
    rows = db.execute(
        'SELECT s.specimen_id, s.shift_id, s.local_id, s.shared_key, o.microns_hex '
        'FROM observations AS o JOIN specimens AS s USING (specimen_id) '
        'WHERE o.revision_id = ? ORDER BY s.local_id',
        (revision_id,),
    )
    return tuple(Observation(SpecimenRef(*row[:4]), int(row[4], 16)) for row in rows)
