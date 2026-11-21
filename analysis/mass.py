from collections.abc import Iterator
from dataclasses import dataclass
from fractions import Fraction
from itertools import combinations
from math import comb

from exchange.evidence import LayerEvidence, SamplingEvidence


@dataclass(frozen=True)
class SelectionMass:
    shared: frozenset[str]
    total: Fraction
    clean: Fraction


def layer_mass(layer: LayerEvidence) -> Iterator[SelectionMass]:
    private_size = layer.private_normal + layer.private_abnormal
    denominator = comb(layer.size, layer.quota)
    least_shared = max(0, layer.quota - private_size)
    most_shared = min(len(layer.shared), layer.quota)
    for shared_count in range(least_shared, most_shared + 1):
        private_take = layer.quota - shared_count
        ways = comb(private_size, private_take)
        clean_private_ways = comb(layer.private_normal, private_take)
        for selected in combinations(layer.shared, shared_count):
            keys = frozenset(mark.key for mark in selected)
            clean_ways = 0 if any(mark.abnormal for mark in selected) else clean_private_ways
            yield SelectionMass(keys, Fraction(ways, denominator), Fraction(clean_ways, denominator))


def shift_mass(evidence: SamplingEvidence) -> tuple[SelectionMass, ...]:
    outcomes = (SelectionMass(frozenset(), Fraction(1), Fraction(1)),)
    for layer in evidence.layers:
        classes = tuple(layer_mass(layer))
        outcomes = tuple(
            SelectionMass(
                left.shared | right.shared,
                left.total * right.total,
                left.clean * right.clean,
            )
            for left in outcomes
            for right in classes
        )
    return outcomes
