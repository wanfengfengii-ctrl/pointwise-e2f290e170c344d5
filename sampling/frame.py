from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from ledger import InvalidInput, require_key
from register.observations import Observation
from register.revisions import ReadingRevision
from sampling.grading import grade_observation
from sampling.protocols import ProtocolVersion


@dataclass(frozen=True)
class FrameSpecimen:
    observation: Observation
    abnormal: bool


@dataclass(frozen=True)
class LayerFrame:
    name: str
    specimens: tuple[FrameSpecimen, ...]


def build_frame(
    revision: ReadingRevision, protocol: ProtocolVersion, layers: Mapping[str, Sequence[str]]
) -> tuple[LayerFrame, ...]:
    if revision.shift_id != protocol.shift_id:
        raise InvalidInput('revision and protocol must belong to the same shift')
    if not isinstance(layers, Mapping):
        raise InvalidInput('layers must be a map')
    by_local_id = {row.specimen.local_id: row for row in revision.observations}
    seen = set()
    frames = []
    for layer_name, entries in layers.items():
        name = require_key(layer_name, 'layer')
        if not isinstance(entries, Sequence) or isinstance(entries, (str, bytes, bytearray)):
            raise InvalidInput(f'layer {name!r} needs a sequence of local specimen IDs')
        specimens = []
        for entry in entries:
            local_id = require_key(entry, 'local_id')
            observation = by_local_id.get(local_id)
            if observation is None:
                raise InvalidInput(f'specimen {local_id!r} has no reading in the pinned revision')
            physical_key = observation.specimen.physical_key
            if physical_key in seen:
                raise InvalidInput(f'physical specimen {local_id!r} occurs more than once in the frame')
            seen.add(physical_key)
            specimens.append(FrameSpecimen(observation, grade_observation(observation, protocol)))
        specimens.sort(key=lambda member: member.observation.specimen.local_id)
        frames.append(LayerFrame(name, tuple(specimens)))
    return tuple(sorted(frames, key=lambda frame: frame.name))
