from dataclasses import dataclass

from ledger import InvalidInput, require_key


@dataclass(frozen=True)
class SharedMark:
    key: str
    abnormal: bool


@dataclass(frozen=True)
class LayerEvidence:
    name: str
    quota: int
    shared: tuple[SharedMark, ...]
    private_normal: int
    private_abnormal: int

    @property
    def size(self) -> int:
        return len(self.shared) + self.private_normal + self.private_abnormal


@dataclass(frozen=True)
class SamplingEvidence:
    layers: tuple[LayerEvidence, ...]

    @property
    def sample_size(self) -> int:
        return sum(layer.quota for layer in self.layers)


def validate_evidence(evidence: SamplingEvidence) -> None:
    if not isinstance(evidence, SamplingEvidence) or not isinstance(evidence.layers, tuple):
        raise InvalidInput('sampling evidence must contain a tuple of layers')
    layer_names = set()
    shared_keys = set()
    for layer in evidence.layers:
        if not isinstance(layer, LayerEvidence) or not isinstance(layer.shared, tuple):
            raise InvalidInput('invalid layer evidence')
        name = require_key(layer.name, 'evidence layer name')
        if name in layer_names:
            raise InvalidInput(f'duplicate evidence layer {name!r}')
        layer_names.add(name)
        for value in (layer.private_normal, layer.private_abnormal):
            if type(value) is not int or value < 0:
                raise InvalidInput('private specimen counts must be nonnegative integers')
        if type(layer.quota) is not int or not 0 <= layer.quota <= layer.size:
            raise InvalidInput(f'evidence quota for layer {name!r} is outside its capacity')
        for mark in layer.shared:
            if not isinstance(mark, SharedMark) or type(mark.abnormal) is not bool:
                raise InvalidInput('shared specimens require a local Boolean abnormal mark')
            key = require_key(mark.key, 'evidence shared key')
            if key in shared_keys:
                raise InvalidInput(f'duplicate evidence shared key {key!r}')
            shared_keys.add(key)
