"""Exact four-cell masses for the paired two-version review.

The paired shift (A) is enumerated layer by layer over its shared-key
subsets and the joint private categories. The other shift (B) reuses the
version-1 single-version mass enumeration. Every draw keeps its original
probability; no random sampling is used.
"""
from dataclasses import dataclass
from fractions import Fraction
from itertools import combinations, product
from math import comb

from analysis.mass import shift_mass
from exchange.evidence import SamplingEvidence
from exchange.paired_evidence import PairedEvidence, PairedLayerEvidence


@dataclass(frozen=True)
class PairedSelectionMass:
    shared: frozenset[str]
    total: Fraction
    # Cells indexed 2*old_detected + new_detected for this selection alone.
    cells: tuple[Fraction, Fraction, Fraction, Fraction]


def _comb(pool: int, take: int) -> int:
    if take < 0 or take > pool:
        return 0
    return comb(pool, take)


def _paired_layer_mass(layer: PairedLayerEvidence) -> list[PairedSelectionMass]:
    pools = (layer.private_00, layer.private_01, layer.private_10, layer.private_11)
    denominator = comb(layer.size, layer.quota)
    private_size = sum(pools)
    least_shared = max(0, layer.quota - private_size)
    most_shared = min(len(layer.shared), layer.quota)
    outcomes = []
    for shared_count in range(least_shared, most_shared + 1):
        private_take = layer.quota - shared_count
        for selected in combinations(layer.shared, shared_count):
            keys = frozenset(mark.key for mark in selected)
            old_shared_bad = any(mark.old_abnormal for mark in selected)
            new_shared_bad = any(mark.new_abnormal for mark in selected)
            cells = [Fraction(0), Fraction(0), Fraction(0), Fraction(0)]
            total_ways = 0
            ranges = [range(min(pool, private_take) + 1) for pool in pools]
            for takes in product(*ranges):
                if sum(takes) != private_take:
                    continue
                ways = 1
                for pool, take in zip(pools, takes):
                    ways *= _comb(pool, take)
                if ways == 0:
                    continue
                old_bad = old_shared_bad or takes[2] > 0 or takes[3] > 0
                new_bad = new_shared_bad or takes[1] > 0 or takes[3] > 0
                index = (2 if old_bad else 0) + (1 if new_bad else 0)
                cells[index] += Fraction(ways, denominator)
                total_ways += ways
            outcomes.append(
                PairedSelectionMass(keys, Fraction(total_ways, denominator), tuple(cells))
            )
    return outcomes


def paired_shift_mass(evidence: PairedEvidence) -> tuple[PairedSelectionMass, ...]:
    neutral = PairedSelectionMass(frozenset(), Fraction(1), (Fraction(1), Fraction(0), Fraction(0), Fraction(0)))
    outcomes: tuple[PairedSelectionMass, ...] = (neutral,)
    for layer in evidence.layers:
        classes = tuple(_paired_layer_mass(layer))
        merged = []
        for left in outcomes:
            for right in classes:
                cells = [Fraction(0)] * 4
                for i, j in product(range(4), range(4)):
                    cells[i | j] += left.cells[i] * right.cells[j]
                merged.append(
                    PairedSelectionMass(
                        left.shared | right.shared,
                        left.total * right.total,
                        tuple(cells),
                    )
                )
        outcomes = tuple(merged)
    return outcomes


@dataclass(frozen=True)
class PairedJointMass:
    condition: Fraction
    cell_masses: tuple[Fraction, Fraction, Fraction, Fraction] | None


def paired_condition_mass(
    paired: PairedEvidence, other: SamplingEvidence, m: int
) -> PairedJointMass:
    total_draws = paired.sample_size + other.sample_size
    condition = Fraction(0)
    cell_masses = [Fraction(0)] * 4
    paired_classes = paired_shift_mass(paired)
    other_classes = shift_mass(other)
    for a in paired_classes:
        for b in other_classes:
            distinct = total_draws - len(a.shared & b.shared)
            if distinct != m:
                continue
            clean_weight = b.clean
            abnormal_weight = b.total - b.clean
            condition += a.total * b.total
            for index, cell in enumerate(a.cells):
                # B draws with no abnormality keep A's two-version cell as is.
                cell_masses[index] += cell * clean_weight
                # B abnormality counts as a detection under both versions.
                cell_masses[index | 3] += cell * abnormal_weight
    if condition == 0:
        return PairedJointMass(condition, None)
    return PairedJointMass(condition, tuple(cell_masses))
