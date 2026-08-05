"""Validate tokens stored in interaction drug_set_a / drug_set_b."""

from __future__ import annotations

import re

_PROSE_MARKERS = (
    "may_",
    "might_",
    "can_",
    "increase_",
    "decrease_",
    "risk_of_",
    "leading_to_",
    "associated_with_",
    "should_",
    "patients_",
    "therapy_",
    "treatment_",
    "caused_by_",
    "result_in_",
    "results_in_",
    "administration_",
    "concomitant_",
    "hypokalem",
    "hyperkalem",
    "monitoring_",
)


def is_plausible_drug_set_token(token: str) -> bool:
    """True for catalog drug keys or class:* tokens — not slugged prose."""
    text = str(token or "").strip().lower()
    if not text:
        return False
    if text.startswith("class:"):
        body = text[6:].strip("_")
        return 2 <= len(body) <= 48 and re.fullmatch(r"[a-z0-9_]+", body or "") is not None
    if len(text) > 36 or text.count("_") > 4:
        return False
    if any(marker in text for marker in _PROSE_MARKERS):
        return False
    if re.search(r"\d{3,}", text):
        return False
    return bool(re.fullmatch(r"[a-z0-9_+-]+", text))


def filter_plausible_drug_set(values: list[str] | None) -> list[str]:
    out: list[str] = []
    for item in values or []:
        token = str(item or "").strip().lower().replace(" ", "_")
        if token and is_plausible_drug_set_token(token) and token not in out:
            out.append(token)
    return out
