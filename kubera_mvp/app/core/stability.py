"""
KUBERA — Decision Stability module (the "Probe Test").

KUBERA does not replace the bank's model. Here we stand in for "the bank's
existing AI" with a small, explicit, deterministic scoring function so the
whole pipeline is runnable end-to-end in this POC. In a real deployment,
`bank_ai_decision()` is swapped for a call into the bank's actual model
(see Slide 6 — Next: Live bank-model API integration).

The Probe Test:
  1. Run the bank AI once on the case as submitted.
  2. Apply a small, realistic perturbation to a non-decisive input field
     (e.g. +/-3% on stated monthly expenses, a rounding-level change).
  3. Re-run the same bank AI on the perturbed case.
  4. If the decision flips, or confidence swings sharply, the original
     recommendation was not stable — regardless of how confident it looked.
"""
from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Dict, Any


def _sigmoid(x: float) -> float:
    import math
    return 1 / (1 + math.exp(-x))


def bank_ai_decision(features: Dict[str, Any]) -> Dict[str, Any]:
    """A small deterministic stand-in for 'the bank's existing AI model'.

    features: {
        monthly_income, monthly_expenses, requested_amount,
        credit_history_score (0-1), employment_years
    }
    Returns {decision: 'APPROVE'|'REJECT', confidence: float 0-1, raw_score: float}
    """
    income = features.get("monthly_income", 0)
    expenses = features.get("monthly_expenses", 0)
    requested = features.get("requested_amount", 0)
    credit = features.get("credit_history_score", 0.5)
    tenure = features.get("employment_years", 0)

    disposable = income - expenses
    affordability = disposable / max(requested, 1) if requested else 1.0

    # A simple linear score the "bank AI" thresholds on. This is deliberately
    # basic — the point of the demo is the probe mechanism, not this model.
    raw_score = (
        1.8 * min(affordability, 3)
        + 2.5 * credit
        + 0.15 * min(tenure, 10)
        - 1.0
    )
    confidence = _sigmoid(raw_score)
    decision = "APPROVE" if confidence >= 0.5 else "REJECT"
    shown_confidence = confidence if decision == "APPROVE" else (1 - confidence)

    return {
        "decision": decision,
        "confidence": round(float(shown_confidence), 3),
        "raw_score": round(float(raw_score), 3),
    }


def perturb_features(features: Dict[str, Any], seed: int = 7) -> Dict[str, Any]:
    """Apply one small, realistic perturbation to a non-decisive field.

    We nudge stated monthly expenses by a small percentage — the kind of
    rounding/estimation noise that legitimately exists in self-reported
    figures and should NOT flip a well-supported decision.
    """
    rng = random.Random(seed)
    pct = rng.uniform(0.03, 0.06)  # 3-6%
    sign = rng.choice([-1, 1])

    perturbed = dict(features)
    perturbed["monthly_expenses"] = round(
        features.get("monthly_expenses", 0) * (1 + sign * pct), 2
    )
    return perturbed, {"field": "monthly_expenses", "change_pct": round(sign * pct * 100, 1)}


@dataclass
class StabilityResult:
    stability_score: float          # 0..1, higher = more stable
    original: Dict[str, Any] = field(default_factory=dict)
    perturbed: Dict[str, Any] = field(default_factory=dict)
    perturbation: Dict[str, Any] = field(default_factory=dict)
    flipped: bool = False
    note: str = ""


def run_probe_test(features: Dict[str, Any]) -> StabilityResult:
    original = bank_ai_decision(features)
    perturbed_features, perturbation = perturb_features(features)
    perturbed = bank_ai_decision(perturbed_features)

    flipped = original["decision"] != perturbed["decision"]
    confidence_swing = abs(original["confidence"] - perturbed["confidence"])

    if flipped:
        stability_score = 0.0
        note = (f"Decision flipped from {original['decision']} to {perturbed['decision']} "
                f"after a {abs(perturbation['change_pct'])}% change to "
                f"{perturbation['field']}. The original recommendation is NOT stable.")
    else:
        # Stable decision, but still penalize large confidence swings.
        stability_score = max(0.0, 1.0 - confidence_swing * 2.5)
        note = (f"Decision held ({original['decision']}) under the probe, "
                f"with a confidence swing of {round(confidence_swing * 100, 1)} points.")

    return StabilityResult(
        stability_score=round(float(stability_score), 3),
        original=original,
        perturbed=perturbed,
        perturbation=perturbation,
        flipped=flipped,
        note=note,
    )
