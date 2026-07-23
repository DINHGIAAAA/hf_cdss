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


def _normalize_numeric_condition(raw: dict[str, Any], key: str, aliases: tuple[str, ...] = ()) -> str | None:
    value = raw.get(key)
    for alias in aliases:
        if value is None:
            value = raw.get(alias)
    if isinstance(value, str) and value.strip():
        return value.strip()
    if isinstance(value, dict):
        return _format_threshold(value.get("op"), value.get("value") or value)
    if value is not None:
        return _format_threshold(None, value)
    return None


def _coerce_bool(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    if isinstance(value, str) and value.strip():
        lowered = value.strip().lower()
        if lowered in {"true", "yes", "1"}:
            return True
        if lowered in {"false", "no", "0"}:
            return False
    return None


def normalize_conditions(raw: dict[str, Any] | None) -> dict[str, Any]:
    if not raw:
        return {}

    condition: dict[str, Any] = {}

    for key, aliases in (
        ("egfr", ()),
        ("potassium", ()),
        ("creatinine", ()),
        ("systolic_bp", ("sbp", "systolic_blood_pressure")),
        ("heart_rate", ("hr", "pulse")),
        ("lvef", ("ejection_fraction",)),
        ("age", ()),
        ("weight_kg", ("weight",)),
        ("ckd_stage", ()),
    ):
        formatted = _normalize_numeric_condition(raw, key, aliases)
        if formatted:
            condition[key] = formatted

    indication = raw.get("indication")
    if isinstance(indication, str) and indication.strip():
        condition["indication"] = _normalize_indication(indication)

    diabetes_type = raw.get("diabetes_type")
    if isinstance(diabetes_type, str) and diabetes_type.strip():
        condition["diabetes_type"] = diabetes_type.strip().lower().replace(" ", "_")

    nyha = raw.get("nyha_class") or raw.get("nyha")
    if isinstance(nyha, str) and nyha.strip():
        condition["nyha_class"] = nyha.strip().upper().replace(" ", "")
    elif isinstance(nyha, (int, float)):
        condition["nyha_class"] = f"NYHA_{int(nyha)}"

    pregnancy = _coerce_bool(raw.get("pregnancy"))
    if pregnancy is True:
        condition["pregnancy"] = True

    lactation = _coerce_bool(raw.get("lactation"))
    if lactation is True:
        condition["lactation"] = True

    allergy = raw.get("allergy") or raw.get("hypersensitivity")
    if isinstance(allergy, str) and allergy.strip():
        condition["allergy"] = allergy.strip().lower()
    elif isinstance(allergy, bool) and allergy:
        condition["allergy"] = "true"

    bleeding = raw.get("bleeding_risk")
    if isinstance(bleeding, str) and bleeding.strip():
        condition["bleeding_risk"] = bleeding.strip().lower().replace(" ", "_")

    hepatic = raw.get("hepatic_impairment")
    if isinstance(hepatic, str) and hepatic.strip():
        condition["hepatic_impairment"] = hepatic.strip().lower()

    for bool_key in (
        "hfref",
        "decompensated_hf",
        "atrial_fibrillation",
        "inotropic_support",
        "anuria",
        "bilateral_renal_artery_stenosis",
    ):
        value = _coerce_bool(raw.get(bool_key))
        if value is True:
            condition[bool_key] = True

    # Canonicalize af → atrial_fibrillation (do not keep dual keys).
    af = _coerce_bool(raw.get("af"))
    if af is True:
        condition["atrial_fibrillation"] = True

    return condition


def _normalize_indication(value: str) -> str:
    haystack = value.lower().replace("-", "_").replace(" ", "_")
    mapping = {
        "heart_failure": ("heart_failure", "hf", "hfr", "hfp"),
        "decompensated_heart_failure": (
            "decompensated_heart_failure",
            "decompensated_hf",
            "acute_decompensated",
            "adhf",
        ),
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
