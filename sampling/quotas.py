from collections.abc import Mapping
from dataclasses import dataclass

from ledger import InvalidInput
from sampling.frame import LayerFrame


@dataclass(frozen=True)
class LayerQuota:
    layer_name: str
    quota: int


def validate_quotas(
    frames: tuple[LayerFrame, ...], quotas: Mapping[str, int]
) -> tuple[LayerQuota, ...]:
    if not isinstance(quotas, Mapping) or set(quotas) != {frame.name for frame in frames}:
        raise InvalidInput('exactly one explicit quota is required for each layer')
    result = []
    for frame in frames:
        quota = quotas[frame.name]
        if type(quota) is not int or not 0 <= quota <= len(frame.specimens):
            raise InvalidInput(f'quota for layer {frame.name!r} must be between zero and its size')
        result.append(LayerQuota(frame.name, quota))
    return tuple(result)
