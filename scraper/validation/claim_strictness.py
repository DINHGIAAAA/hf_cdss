"""Lenient validation for clinical claims - keep most claims, only filter truly invalid ones."""

from __future__ import annotations

import re
from typing import Any


def is_valid_claim_type(claim_type: str) -> bool:
    """Check if claim type is valid."""
    VALID_TYPES = {
        "contraindication", "renal_constraint", "usage_constraint",
        "hyperkalemia_risk", "dose_recommendation", "drug_interaction",
        "adverse_reaction", "population_constraint", "guideline_recommendation",
        "general_monitoring"
    }
    return claim_type in VALID_TYPES


def is_meaningful_evidence(evidence: str) -> bool:
    """Check if evidence is meaningful (not too short or empty)."""
    if not evidence or len(evidence.strip()) < 15:
        return False
    return True


def validate_claim(claim: dict[str, Any]) -> tuple[bool, str]:
    """Validate a single claim.

    Returns: (is_valid, reason)
    """
    evidence = claim.get("evidence", "")
    claim_type = claim.get("claim_type", "")

    if not is_meaningful_evidence(evidence):
        return False, "evidence_too_short"

    if not claim_type:
        return False, "missing_claim_type"

    if not is_valid_claim_type(claim_type):
        return False, f"invalid_claim_type:{claim_type}"

    return True, ""


def filter_strict_claims(claims: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Filter only clearly invalid claims - LENIENT filtering.

    Only removes claims that are clearly invalid (wrong type, too short, etc).
    """
    filtered = []

    for claim in claims:
        is_valid, reason = validate_claim(claim)
        if is_valid:
            filtered.append(claim)

    return filtered


def validate_all_claims(
    claims: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Validate all claims."""
    return [
        {"claim_id": c.get("claim_id"), **({"valid": True} if validate_claim(c)[0] else {"valid": False, "reason": validate_claim(c)[1]})}
        for c in claims
    ]
