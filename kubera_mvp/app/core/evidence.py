"""
KUBERA — Evidence module.

Retrieves the policy clause(s) and historical case(s) most relevant to why
a case was escalated, so a human reviewer never sees a bare number — they
see the reasoning trail. This POC uses tag-overlap retrieval (explicit,
auditable) rather than a learned embedding/RAG model, per the constraint
that we do not claim RAG/LLM functionality unless it is actually implemented.
"""
from __future__ import annotations

import json
import os
from typing import List, Dict, Any

_BASE = os.path.join(os.path.dirname(__file__), "..", "..", "data")


def _load(name: str) -> List[Dict[str, Any]]:
    path = os.path.join(_BASE, name)
    with open(path, "r") as f:
        return json.load(f)


def _score_overlap(item_tags: List[str], query_tags: List[str]) -> float:
    if not item_tags or not query_tags:
        return 0.0
    a, b = set(item_tags), set(query_tags)
    return len(a & b) / len(a | b)


def find_evidence(query_tags: List[str], top_k_policies: int = 1, top_k_cases: int = 1) -> Dict[str, Any]:
    policies = _load(os.path.join("policies", "policies.json"))
    cases = _load(os.path.join("cases", "cases.json"))

    scored_policies = sorted(
        policies, key=lambda p: _score_overlap(p.get("tags", []), query_tags), reverse=True
    )
    scored_cases = sorted(
        cases, key=lambda c: _score_overlap(c.get("tags", []), query_tags), reverse=True
    )

    top_policies = [
        {**p, "similarity": round(_score_overlap(p.get("tags", []), query_tags), 2)}
        for p in scored_policies[:top_k_policies]
    ]
    top_cases = [
        {**c, "similarity": round(_score_overlap(c.get("tags", []), query_tags), 2)}
        for c in scored_cases[:top_k_cases]
    ]

    return {"policies": top_policies, "similar_cases": top_cases}
