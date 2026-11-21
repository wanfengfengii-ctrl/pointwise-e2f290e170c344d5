"""Evidence carried by a version-2 paired batch.

A paired batch freezes the two versions of one shift's sampling frame.
Shared specimens carry both version marks; private specimens stay on the
station and only their joint category counts leave it.
"""
from dataclasses import dataclass

from exchange.evidence import SharedMark
from ledger import InvalidInput, require_key


@dataclass(frozen=True)
class PairedSharedMark:
    key: str
    old_abnormal: bool
    new_abnormal: bool


@dataclass(frozen=True)
class PairedLayerEvidence:
    name: str
    quota: int
    # Frozen frame size, recorded on the station as an evidence checksum.
    size_declared: int
    shared: tuple[PairedSharedMark, ...]
    # Joint private categories under (old, new): (0,0), (0,1), (1,0), (1,1).
    private_00: int
    private_01: int
    private_10: int
    private_11: int

    @property
    def private_normal(self) -> int:
        """Private pieces normal under the old version."""
        return self.private_00 + self.private_01

    @property
    def private_abnormal(self) -> int:
        """Private pieces abnormal under the old version."""
        return self.private_10 + self.private_11

    @property
    def new_private_normal(self) -> int:
        return self.private_00 + self.private_10

    @property
    def new_private_abnormal(self) -> int:
        return self.private_01 + self.private_11

    @property
    def private_size(self) -> int:
        return self.private_00 + self.private_01 + self.private_10 + self.private_11

    @property
    def size(self) -> int:
        return self.size_declared


@dataclass(frozen=True)
class PairedEvidence:
    layers: tuple[PairedLayerEvidence, ...]

    @property
    def sample_size(self) -> int:
        return sum(layer.quota for layer in self.layers)


def _require_int(value: object, field: str) -> int:
    if type(value) is not int or value < 0:
        raise InvalidInput(f'{field} must be a nonnegative integer')
    return value


def validate_paired_evidence(evidence: PairedEvidence) -> None:
    if not isinstance(evidence, PairedEvidence) or not isinstance(evidence.layers, tuple):
        raise InvalidInput('paired evidence must contain a tuple of layers')
    layer_names = set()
    shared_keys = set()
    for layer in evidence.layers:
        if not isinstance(layer, PairedLayerEvidence) or not isinstance(layer.shared, tuple):
            raise InvalidInput('invalid paired layer evidence')
        name = require_key(layer.name, 'paired evidence layer name')
        if name in layer_names:
            raise InvalidInput(f'duplicate paired evidence layer {name!r}')
        layer_names.add(name)
        for field, value in (
            ('size_declared', layer.size_declared),
            ('private_00', layer.private_00),
            ('private_01', layer.private_01),
            ('private_10', layer.private_10),
            ('private_11', layer.private_11),
        ):
            _require_int(value, field)
        # The recorded frame size must equal every piece named by the evidence.
        if layer.size_declared != len(layer.shared) + layer.private_size:
            raise InvalidInput(
                f'paired evidence for layer {name!r} is inconsistent with its frozen frame size'
            )
        if type(layer.quota) is not int or not 0 <= layer.quota <= layer.size:
            raise InvalidInput(f'paired evidence quota for layer {name!r} is outside its capacity')
        for mark in layer.shared:
            if not isinstance(mark, PairedSharedMark):
                raise InvalidInput('paired shared marks must use the paired mark type')
            if type(mark.old_abnormal) is not bool or type(mark.new_abnormal) is not bool:
                raise InvalidInput('paired shared specimens require two local Boolean marks')
            key = require_key(mark.key, 'paired evidence shared key')
            if key in shared_keys:
                raise InvalidInput(f'duplicate paired evidence shared key {key!r}')
            shared_keys.add(key)


def as_old_shared(mark: PairedSharedMark) -> SharedMark:
    return SharedMark(mark.key, mark.old_abnormal)


def as_new_shared(mark: PairedSharedMark) -> SharedMark:
    return SharedMark(mark.key, mark.new_abnormal)
