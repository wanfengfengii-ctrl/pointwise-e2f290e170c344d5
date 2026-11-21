from collections.abc import Mapping, Sequence
from dataclasses import dataclass
import sqlite3

from ledger import InvalidInput, UnknownRecord, require_id, require_key, transaction
from register.revisions import load_revision
from sampling.frame import FrameSpecimen, LayerFrame, build_frame
from sampling.protocols import load_protocol
from sampling.quotas import LayerQuota, validate_quotas


@dataclass(frozen=True)
class FrozenDesign:
    design_id: int
    shift_id: str
    revision_id: int
    protocol_version: str
    layers: tuple[LayerFrame, ...]
    quotas: tuple[LayerQuota, ...]


def freeze(
    db: sqlite3.Connection,
    shift_id: str,
    revision_id: int,
    protocol_version: str,
    layers: Mapping[str, Sequence[str]],
    quotas: Mapping[str, int],
) -> int:
    shift_id = require_key(shift_id, 'shift_id')
    with transaction(db, allow_nested=True):
        revision = load_revision(db, revision_id)
        if revision.shift_id != shift_id:
            raise InvalidInput('the pinned revision belongs to another shift')
        protocol = load_protocol(db, shift_id, protocol_version)
        frames = build_frame(revision, protocol, layers)
        checked_quotas = validate_quotas(frames, quotas)
        cursor = db.execute(
            'INSERT INTO designs(shift_id, revision_id, protocol_version) VALUES (?, ?, ?)',
            (shift_id, revision_id, protocol.version),
        )
        design_id = cursor.lastrowid
        db.executemany(
            'INSERT INTO design_layers(design_id, layer_name, quota) VALUES (?, ?, ?)',
            ((design_id, quota.layer_name, quota.quota) for quota in checked_quotas),
        )
        db.executemany(
            'INSERT INTO frame_members(design_id, layer_name, specimen_id, abnormal) VALUES (?, ?, ?, ?)',
            (
                (design_id, frame.name, member.observation.specimen.specimen_id, member.abnormal)
                for frame in frames
                for member in frame.specimens
            ),
        )
    return design_id


def load_design(db: sqlite3.Connection, design_id: int) -> FrozenDesign:
    design_id = require_id(design_id, 'design_id')
    row = db.execute(
        'SELECT shift_id, revision_id, protocol_version FROM designs WHERE design_id = ?',
        (design_id,),
    ).fetchone()
    if row is None:
        raise UnknownRecord(f'unknown design {design_id}')
    shift_id, revision_id, protocol_version = row
    observations = {
        item.specimen.specimen_id: item for item in load_revision(db, revision_id).observations
    }
    quotas = tuple(
        LayerQuota(*entry)
        for entry in db.execute(
            'SELECT layer_name, quota FROM design_layers WHERE design_id = ? ORDER BY layer_name',
            (design_id,),
        )
    )
    by_layer = {quota.layer_name: [] for quota in quotas}
    for layer_name, specimen_id, abnormal in db.execute(
        'SELECT f.layer_name, f.specimen_id, f.abnormal '
        'FROM frame_members AS f JOIN specimens AS s USING (specimen_id) '
        'WHERE f.design_id = ? ORDER BY s.local_id',
        (design_id,),
    ):
        by_layer[layer_name].append(FrameSpecimen(observations[specimen_id], bool(abnormal)))
    frames = tuple(LayerFrame(name, tuple(members)) for name, members in by_layer.items())
    return FrozenDesign(design_id, shift_id, revision_id, protocol_version, frames, quotas)
