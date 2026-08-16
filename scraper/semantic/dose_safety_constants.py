"""Shared constants for dose safety claim filtering and classification."""

from __future__ import annotations

import re
from typing import Any

# Patient fields the runtime dose-safety evaluator actually knows how to read.
# A condition field outside this set (e.g. an LLM-hallucinated "age" or
# "weight_kg") can never fire safely and must not reach the catalog.
EVALUATOR_FIELDS = frozenset(
    {"egfr", "crcl", "creatinine", "potassium", "systolic_bp", "heart_rate"}
)

# LLM refusal / non-informative patterns
_REFUSAL_RE = re.compile(
    r"(does not contain|no specific evidence|no dosage|not contain any dosage|"
    r"cannot extract|no evidence for|not enough (text|evidence|information)|"
    r"not available|no specific dosage|no established dose|insufficient evidence|"
    r"not recommended|not applicable|no specific (contraindication|warning|safety))",
    re.IGNORECASE,
)

# Clinical keywords that indicate a real safety/monitoring signal.
# superset of both semantic/ and process/ versions.
_SAFETY_CUES = (
    "renal",
    "egfr",
    "crcl",
    "creatinine",
    "potassium",
    "hyperkal",
    "hypokal",
    "k+",
    "serum k",
    "hold",
    "hold if",
    "hold dose",
    "reduce dose",
    "dose reduction",
    "dose adjustment",
    "hepatic",
    "heart rate",
    "bradycardia",
    "hypotension",
    "systolic",
    "lab monitoring",
    "monitor potassium",
    "monitor renal",
    "renal function",
    "bleeding",
    "bleeding risk",
    "qtc",
    "qt prolongation",
    "worsening hf",
    "decompensation",
    "shock",
    "hypoperfusion",
    "angioedema",
)


def is_refusal_message(text: str | None) -> bool:
    return bool(_REFUSAL_RE.search(str(text or "")))


def has_safety_cue(text: str) -> bool:
    lowered = text.lower()
    return any(cue in lowered for cue in _SAFETY_CUES)


def trigger_is_always_only(trigger: Any) -> bool:
    """True when trigger has no patient-condition gates (only operator=always)."""
    if not isinstance(trigger, dict):
        return True
    groups = trigger.get("condition_groups")
    if not isinstance(groups, list) or not groups:
        return True
    flat: list[dict[str, Any]] = []
    for group in groups:
        if isinstance(group, list):
            flat.extend(item for item in group if isinstance(item, dict))
        elif isinstance(group, dict):
            flat.append(group)
    if not flat:
        return True
    return all(str(item.get("operator") or "").lower() == "always" for item in flat)
