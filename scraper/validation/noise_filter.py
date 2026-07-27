"""Balanced noise filter - removes obvious noise while keeping most clinical claims."""

from __future__ import annotations

import logging
import re
from typing import Any

logger = logging.getLogger(__name__)

# Patterns that are ALWAYS noise (not clinical guidance)
ABSOLUTE_NOISE_PATTERNS = [
    # Statistical results - clearly not clinical guidance
    re.compile(r"incidence\s+of\s+\d+\s*%", re.IGNORECASE),
    re.compile(r"p\s*[<>]\s*0?\.\d+", re.IGNORECASE),
    re.compile(r"hazard\s+ratio", re.IGNORECASE),
    re.compile(r"odds\s+ratio", re.IGNORECASE),
    re.compile(r"confidence\s+interval", re.IGNORECASE),
    re.compile(r"statistically\s+significant", re.IGNORECASE),

    # Study/Trial descriptions
    re.compile(r"randomized\s+controlled\s+trial", re.IGNORECASE),
    re.compile(r"\brct\b", re.IGNORECASE),
    re.compile(r"double-blind", re.IGNORECASE),
    re.compile(r"placebo-controlled", re.IGNORECASE),

    # Label only (no clinical guidance)
    re.compile(r"pregnancy\s+category\s+[a-z]", re.IGNORECASE),
    re.compile(r"category\s+[a-z]\s+pregnancy", re.IGNORECASE),

    # Table/Figure references alone (not guidance)
    re.compile(r"^table\s+\d+", re.IGNORECASE),
    re.compile(r"^figure\s+\d+", re.IGNORECASE),
]

# Patterns that are noise ONLY if no clinical keywords nearby
CONTEXTUAL_NOISE_PATTERNS = [
    "clinical trial",
    "study showed",
    "pharmacokinetic",
    "bioavailability",
    "half-life",
]

# Clinical keywords that indicate valid clinical guidance
CLINICAL_KEYWORDS = [
    "dose", "dosage", "mg", "administer", "start", "stop", "reduce",
    "contraindication", "contraindicated", "warning", "precaution",
    "avoid", "monitor", "check", "measure", "renal", "hepatic",
    "pregnancy", "pregnant", "interact", "interaction", "hyperkalemia",
    "potassium", "creatinine", "egfr", "adverse", "reaction",
    "risk", "caution", "recommended", "indicated", "adjust",
    "increase", "decrease", "withhold", "discontinue",
]


def has_clinical_keyword(text: str) -> bool:
    """Check if text has clinical guidance keywords."""
    text_lower = text.lower()
    return any(kw in text_lower for kw in CLINICAL_KEYWORDS)


def is_absolute_noise(evidence: str) -> tuple[bool, str]:
    """Check if evidence is clearly noise (no clinical value)."""
    for pattern in ABSOLUTE_NOISE_PATTERNS:
        if pattern.search(evidence):
            return True, pattern.pattern
    return False, ""


def filter_noise_claims(claims: list[dict]) -> list[dict]:
    """Balanced filter - removes obvious noise, keeps most clinical claims."""
    filtered = []
    removed = 0

    for claim in claims:
        evidence = claim.get("evidence", "")
        claim_type = claim.get("claim_type", "")

        if not evidence or len(evidence.strip()) < 15:
            removed += 1
            continue

        # Check absolute noise patterns
        is_noise, pattern = is_absolute_noise(evidence)
        if is_noise:
            # But keep if it has clinical keywords
            if has_clinical_keyword(evidence):
                filtered.append(claim)
            else:
                removed += 1
            continue

        filtered.append(claim)

    if removed > 0:
        logger.info(f"Filtered {removed}/{len(claims)} noise claims")

    return filtered


def filter_strict_claims(claims: list[dict]) -> list[dict]:
    """Lenient filter - only removes invalid claim types."""
    VALID_TYPES = {
        "contraindication", "renal_constraint", "usage_constraint",
        "hyperkalemia_risk", "dose_recommendation", "drug_interaction",
        "adverse_reaction", "population_constraint", "guideline_recommendation",
        "general_monitoring"
    }

    filtered = []
    for claim in claims:
        if claim.get("claim_type") in VALID_TYPES:
            filtered.append(claim)
    return filtered
