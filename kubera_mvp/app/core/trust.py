"""
KUBERA — Unified Trust Score.

Combines the three signal families (Input Integrity, Decision Stability,
Evidence/Policy Alignment) into one score in [0, 100] and a routing
decision. Weights are explicit and easy to defend to a judge or a
compliance reviewer — no hidden black-box aggregation.
"""
from __future__ import annotations

from dataclasses import dataclass

W_INTEGRITY = 0.35
W_STABILITY = 0.35
W_POLICY = 0.15
W_EVIDENCE = 0.15

PROCEED_THRESHOLD = 75
MONITOR_THRESHOLD = 45


@dataclass
class TrustResult:
    trust_score: int
    route: str          # PROCEED | MONITOR | HUMAN_REVIEW
    breakdown: dict


def compute_policy_alignment(affordability_ratio: float) -> float:
    """How well the case aligns with a simple, explicit affordability policy
    (POL-2.5: affordability ratio should be >= 1.2x)."""
    if affordability_ratio >= 1.2:
        return 1.0
    if affordability_ratio <= 0:
        return 0.0
    return max(0.0, affordability_ratio / 1.2)


def compute_evidence_consistency(similar_cases: list) -> float:
    """Higher when the best-matching historical case's outcome is favorable
    and similarity is high; lower when the closest precedent was fraud."""
    if not similar_cases:
        return 0.5
    top = similar_cases[0]
    sim = top.get("similarity", 0)
    bad_outcomes = {"CONFIRMED_FRAUD"}
    if top.get("outcome") in bad_outcomes:
        return max(0.0, 1.0 - sim)
    return min(1.0, 0.5 + sim)


def compute_trust_score(integrity_score: float, stability_score: float,
                         policy_alignment: float, evidence_consistency: float) -> TrustResult:
    combined = (
        W_INTEGRITY * integrity_score
        + W_STABILITY * stability_score
        + W_POLICY * policy_alignment
        + W_EVIDENCE * evidence_consistency
    )
    score = int(round(combined * 100))

    if score >= PROCEED_THRESHOLD:
        route = "PROCEED"
    elif score >= MONITOR_THRESHOLD:
        route = "MONITOR"
    else:
        route = "HUMAN_REVIEW"

    return TrustResult(
        trust_score=score,
        route=route,
        breakdown={
            "input_integrity": round(integrity_score, 2),
            "decision_stability": round(stability_score, 2),
            "policy_alignment": round(policy_alignment, 2),
            "evidence_consistency": round(evidence_consistency, 2),
        },
    )
