from dataclasses import dataclass
from fractions import Fraction
import sqlite3

from analysis.overlap import condition_mass
from analysis.request import RiskRequest, resolve_request, validate_distinct_total
from exchange.evidence import SamplingEvidence, validate_evidence
from ledger import InvalidInput
from report.issue import PublishedReport, issue_report


@dataclass(frozen=True)
class RiskResult:
    status: str
    condition_mass: Fraction
    zero_probability: Fraction | None


def assess_risk(left: SamplingEvidence, right: SamplingEvidence, m: int) -> RiskResult:
    m = validate_distinct_total(m)
    validate_evidence(left)
    validate_evidence(right)
    mass = condition_mass(left, right, m)
    if not 0 <= mass.zero_joint <= mass.condition <= 1:
        raise InvalidInput('the joint calculation produced inconsistent probability masses')
    if mass.condition == 0:
        return RiskResult('unreachable', mass.condition, None)
    return RiskResult('reachable', mass.condition, mass.zero_joint / mass.condition)


def publish(
    db: sqlite3.Connection, left_receipt_id: int, right_receipt_id: int, m: int | None = None
) -> PublishedReport:
    requested_m = validate_distinct_total(m)
    request = RiskRequest(left_receipt_id, right_receipt_id, requested_m)
    left, right = resolve_request(db, request)
    result = assess_risk(left.packet.evidence, right.packet.evidence, requested_m)
    return issue_report(
        db, requested_m, result.status, result.condition_mass, result.zero_probability, left, right
    )
