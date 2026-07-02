"""Normalize structured clinical conditions for rule evaluation."""

from __future__ import annotations

import re
from typing import Any


def _format_threshold(op: str | None, value: Any, *, unit: str = "") -> str | None:
    if value is None or value == "":
        return None
    op = (op or "").strip().lower()
    if isinstance(value, dict):
        minimum = value.get("min")
        maximum = value.get("max")
        if minimum is not None and maximum is not None:
            return f"{minimum}-{maximum}"
        value = value.get("value", value.get("threshold"))

    if isinstance(value, (int, float)):
        numeric = value
    else:
        text = str(value).strip()
        range_match = re.fullmatch(r"(\d+(?:\.\d+)?)\s*(?:to|-)\s*(\d+(?:\.\d+)?)", text)
        if range_match:
            return f"{range_match.group(1)}-{range_match.group(2)}"
        number_match = re.search(r"(\d+(?:\.\d+)?)", text)
        if not number_match:
            return text or None
        numeric = float(number_match.group(1))

    if op in {"<", "lt", "less_than", "below"}:
        return f"<{numeric:g}"
    if op in {"<=", "lte", "less_or_equal"}:
        return f"<={numeric:g}"
    if op in {">", "gt", "greater_than", "above"}:
        return f">{numeric:g}"
    if op in {">=", "gte", "greater_or_equal"}:
        return f">={numeric:g}"
    return f"{numeric:g}{unit}"


def normalize_conditions(raw: dict[str, Any] | None) -> dict[str, Any]:
    if not raw:
        return {}

    condition: dict[str, Any] = {}

    egfr = raw.get("egfr")
    if isinstance(egfr, str) and egfr.strip():
        condition["egfr"] = egfr.strip()
    elif isinstance(egfr, dict):
        formatted = _format_threshold(egfr.get("op"), egfr.get("value") or egfr)
        if formatted:
            condition["egfr"] = formatted
    elif egfr is not None:
        formatted = _format_threshold(None, egfr)
        if formatted:
            condition["egfr"] = formatted

    potassium = raw.get("potassium")
    if isinstance(potassium, str) and potassium.strip():
        condition["potassium"] = potassium.strip()
    elif isinstance(potassium, dict):
        formatted = _format_threshold(potassium.get("op"), potassium.get("value") or potassium)
        if formatted:
            condition["potassium"] = formatted
    elif potassium is not None:
        formatted = _format_threshold(None, potassium)
        if formatted:
            condition["potassium"] = formatted

    indication = raw.get("indication")
    if isinstance(indication, str) and indication.strip():
        condition["indication"] = _normalize_indication(indication)

    diabetes_type = raw.get("diabetes_type")
    if isinstance(diabetes_type, str) and diabetes_type.strip():
        condition["diabetes_type"] = diabetes_type.strip().lower().replace(" ", "_")

    creatinine = raw.get("creatinine")
    if isinstance(creatinine, dict):
        formatted = _format_threshold(creatinine.get("op"), creatinine.get("value") or creatinine)
        if formatted:
            condition["creatinine"] = formatted

    return condition


def _normalize_indication(value: str) -> str:
    haystack = value.lower().replace("-", "_").replace(" ", "_")
    mapping = {
        "heart_failure": ("heart_failure", "hf", "hfr", "hfp"),
        "glycemic_control": ("glycemic_control", "glycaemic_control", "diabetes", "t2dm"),
        "hypertension": ("hypertension", "blood_pressure"),
        "atrial_fibrillation": ("atrial_fibrillation", "afib", "af"),
        "chronic_kidney_disease": ("chronic_kidney_disease", "ckd", "renal"),
    }
    for canonical, aliases in mapping.items():
        if haystack in aliases or any(alias in haystack for alias in aliases):
            return canonical
    return haystack


def infer_action_from_text(text: str, claim_type: str, explicit_action: str | None = None) -> str:
    if explicit_action:
        normalized = explicit_action.strip().lower().replace(" ", "_")
        allowed = {
            "contraindicated",
            "not_recommended",
            "avoid",
            "monitor",
            "recommended",
            "review",
            "dose_adjust",
            "reduce_dose",
        }
        if normalized in allowed:
            return normalized

    haystack = (text or "").lower()
    if "contraindicated" in haystack or claim_type == "contraindication":
        return "contraindicated"
    if "not recommended" in haystack:
        return "not_recommended"
    if "avoid" in haystack:
        return "avoid"
    if "monitor" in haystack:
        return "monitor"
    if any(term in haystack for term in ("recommended", "should", "is indicated")):
        return "recommended"
    return "review"
