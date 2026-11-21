import sqlite3
from uuid import uuid4

from exchange.codec import BatchPacket, encode_packet
from exchange.evidence import LayerEvidence, SamplingEvidence, SharedMark
from ledger import transaction
from sampling.design import FrozenDesign, load_design


def build_evidence(design: FrozenDesign) -> SamplingEvidence:
    quotas = {item.layer_name: item.quota for item in design.quotas}
    layers = []
    for frame in design.layers:
        shared = []
        private_normal = 0
        private_abnormal = 0
        for member in frame.specimens:
            key = member.observation.specimen.shared_key
            if key is not None:
                shared.append(SharedMark(key, member.abnormal))
            elif member.abnormal:
                private_abnormal += 1
            else:
                private_normal += 1
        shared.sort(key=lambda mark: mark.key)
        layers.append(
            LayerEvidence(frame.name, quotas[frame.name], tuple(shared), private_normal, private_abnormal)
        )
    return SamplingEvidence(tuple(layers))


def issue(db: sqlite3.Connection, design_id: int) -> tuple[str, bytes]:
    with transaction(db, allow_nested=True):
        design = load_design(db, design_id)
        issue_id = uuid4().hex
        packet = BatchPacket(
            issue_id, design.shift_id, design.design_id, design.revision_id,
            design.protocol_version, build_evidence(design),
        )
        wire = encode_packet(packet)
        db.execute(
            'INSERT INTO issued_batches(issue_id, design_id, wire) VALUES (?, ?, ?)',
            (issue_id, design_id, wire),
        )
    return issue_id, wire
