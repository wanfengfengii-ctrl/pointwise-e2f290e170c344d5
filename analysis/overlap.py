from dataclasses import dataclass
from fractions import Fraction

from analysis.mass import shift_mass
from exchange.evidence import SamplingEvidence


@dataclass(frozen=True)
class JointMass:
    condition: Fraction
    zero_joint: Fraction


def distinct_count(total_draws: int, left_shared: frozenset[str], right_shared: frozenset[str]) -> int:
    return total_draws - len(left_shared & right_shared)


def condition_mass(left: SamplingEvidence, right: SamplingEvidence, m: int) -> JointMass:
    left_size = left.sample_size
    right_size = right.sample_size
    total_draws = left_size + right_size
    condition = Fraction(0)
    zero_joint = Fraction(0)
    if max(left_size, right_size) <= m <= total_draws:
        left_classes = shift_mass(left)
        right_classes = shift_mass(right)
        for a in left_classes:
            for b in right_classes:
                if distinct_count(total_draws, a.shared, b.shared) == m:
                    condition += a.total * b.total
                    zero_joint += a.clean * b.clean
    return JointMass(condition, zero_joint)
