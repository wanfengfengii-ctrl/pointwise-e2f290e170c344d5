"""Issue a paired batch binding two exact frozen designs of one shift."""
import sqlite3
from uuid import uuid4

from exchange.paired_codec import PairedPacket, encode_paired_packet
from exchange.paired_evidence import PairedEvidence, PairedLayerEvidence, PairedSharedMark
from ledger import InvalidInput, require_id, transaction
from sampling.design import FrozenDesign, load_design


def _physical_sets(design: FrozenDesign) -> dict[str, set[tuple[str, str | int]]]:
    sets = {}
    for frame in design.layers:
        members = set()
        for member in frame.specimens:
            members.add(member.observation.specimen.physical_key)
        sets[frame.name] = members
    return sets


def _quota_map(design: FrozenDesign) -> dict[str, int]:
    return {item.layer_name: item.quota for item in design.quotas}


def _validate_pair(old: FrozenDesign, new: FrozenDesign) -> None:
    if old.shift_id != new.shift_id:
        raise InvalidInput('a paired batch requires two designs of the same shift')
    old_layers = {frame.name: frame for frame in old.layers}
    new_layers = {frame.name: frame for frame in new.layers}
    if set(old_layers) != set(new_layers):
        raise InvalidInput('the two frozen designs do not share the same layer names')
    old_quotas = _quota_map(old)
    new_quotas = _quota_map(new)
    if old_quotas != new_quotas:
        raise InvalidInput('the two frozen designs do not share the same per-layer quotas')
    old_sets = _physical_sets(old)
    new_sets = _physical_sets(new)
    for name in old_layers:
        if len(old_layers[name].specimens) != len(new_layers[name].specimens):
            raise InvalidInput(f'layer {name!r} does not contain the same number of physical pieces')
        if old_sets[name] != new_sets[name]:
            raise InvalidInput(f'layer {name!r} swaps physical pieces between the two designs')


def _build_paired_evidence(
    old: FrozenDesign, new: FrozenDesign
) -> PairedEvidence:
    new_frames = {frame.name: frame for frame in new.layers}
    layers = []
    for old_frame in old.layers:
        new_frame = new_frames[old_frame.name]
        old_by_key = {
            member.observation.specimen.physical_key: member for member in old_frame.specimens
        }
        new_by_key = {
            member.observation.specimen.physical_key: member for member in new_frame.specimens
        }
        shared = []
        counts = [0, 0, 0, 0]  # (0,0), (0,1), (1,0), (1,1) under (old, new)
        for physical_key, old_member in old_by_key.items():
            new_member = new_by_key[physical_key]
            old_flag = old_member.abnormal
            new_flag = new_member.abnormal
            shared_key = old_member.observation.specimen.shared_key
            if shared_key is not None:
                if new_member.observation.specimen.shared_key != shared_key:
                    raise InvalidInput('a shared physical piece lost its shared identity between designs')
                shared.append(PairedSharedMark(shared_key, old_flag, new_flag))
            else:
                counts[(1 if old_flag else 0) * 2 + (1 if new_flag else 0)] += 1
        shared.sort(key=lambda mark: mark.key)
        layers.append(
            PairedLayerEvidence(
                old_frame.name,
                _quota_map(old)[old_frame.name],
                len(old_frame.specimens),
                tuple(shared),
                counts[0],
                counts[1],
                counts[2],
                counts[3],
            )
        )
    return PairedEvidence(tuple(sorted(layers, key=lambda layer: layer.name)))


def issue_pair(
    db: sqlite3.Connection, old_design_id: int, new_design_id: int
) -> tuple[str, bytes]:
    old_design_id = require_id(old_design_id, 'old_design_id')
    new_design_id = require_id(new_design_id, 'new_design_id')
    with transaction(db, allow_nested=True):
        old = load_design(db, old_design_id)
        new = load_design(db, new_design_id)
        _validate_pair(old, new)
        evidence = _build_paired_evidence(old, new)
        issue_id = uuid4().hex
        packet = PairedPacket(
            issue_id,
            old.shift_id,
            old.design_id,
            old.revision_id,
            old.protocol_version,
            new.design_id,
            new.revision_id,
            new.protocol_version,
            evidence,
        )
        wire = encode_paired_packet(packet)
        cursor = db.execute(
            'INSERT INTO issued_batches(issue_id, design_id, wire) VALUES (?, NULL, ?)',
            (issue_id, wire),
        )
        db.executemany(
            'INSERT INTO pair_issue_designs(issue_id, position, design_id) VALUES (?, ?, ?)',
            ((issue_id, 0, old_design_id), (issue_id, 1, new_design_id)),
        )
    return issue_id, wire
