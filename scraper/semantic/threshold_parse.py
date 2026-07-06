"""Parse numeric threshold phrases from extracted entity text."""

from __future__ import annotations

import re
from typing import Any


_EGFR_PATTERN = re.compile(
    r"\beGFR\b.*?(?:less than|below|<|≤|<=)\s*(\d+(?:\.\d+)?)",
    re.IGNORECASE,
)
_POTASSIUM_PATTERN = re.compile(
    r"\b(?:serum\s+)?potassium\b.*?(?:greater than|above|>|≥|>=)\s*(\d+(?:\.\d+)?)",
    re.IGNORECASE,
)
_GENERIC_THRESHOLD = re.compile(
    r"(?:less than|below|<|≤|<=|greater than|above|>|≥|>=)\s*(\d+(?:\.\d+)?)\s*"
    r"(mL/min/1\.73\s*m\s*2|mg/dL|mmol/L|mmHg|bpm|%)?",
    re.IGNORECASE,
)


def _normalize_operator(operator: str) -> str:
    lowered = operator.lower().strip()
    if lowered in {"less than", "below", "<", "≤", "<="}:
        return "<="
    if lowered in {"greater than", "above", ">", "≥", ">="}:
        return ">="
    return lowered


def parse_threshold_entity(value: str) -> dict[str, Any] | None:
    text = (value or "").strip()
    if not text:
        return None

    match = _EGFR_PATTERN.search(text)
    if match:
        return {
            "metric": "egfr",
            "operator": "<=",
            "value": float(match.group(1)),
            "unit": "mL/min/1.73m2",
            "raw_text": text,
        }

    match = _POTASSIUM_PATTERN.search(text)
    if match:
        return {
            "metric": "potassium",
            "operator": ">=",
            "value": float(match.group(1)),
            "unit": "mmol/L",
            "raw_text": text,
        }

    match = _GENERIC_THRESHOLD.search(text)
    if match:
        operator_token = match.group(0).split(str(match.group(1)), maxsplit=1)[0]
        return {
            "metric": "unknown",
            "operator": _normalize_operator(operator_token),
            "value": float(match.group(1)),
            "unit": (match.group(2) or "").strip() or None,
            "raw_text": text,
        }

    return None
