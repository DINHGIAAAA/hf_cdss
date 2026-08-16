"""Build evaluable dose-safety triggers from structured dose claims and evidence."""

from __future__ import annotations

import re
from typing import Any

from scraper.semantic.dose_safety_constants import EVALUATOR_FIELDS

# Maps hold_if dict keys from dose extraction prompt to evaluator fields/operators.
_HOLD_IF_KEY_MAP: dict[str, tuple[str, str]] = {
    "systolic_bp_lt": ("systolic_bp", "lt"),
    "systolic_bp_lte": ("systolic_bp", "lte"),
    "potassium_gte": ("potassium", "gte"),
    "potassium_gt": ("potassium", "gt"),
    "potassium_lte": ("potassium", "lte"),
    "potassium_lt": ("potassium", "lt"),
    "egfr_lt": ("egfr", "lt"),
    "egfr_lte": ("egfr", "lte"),
    "egfr_gt": ("egfr", "gt"),
    "egfr_gte": ("egfr", "gte"),
    "crcl_lt": ("crcl", "lt"),
    "crcl_lte": ("crcl", "lte"),
    "heart_rate_lt": ("heart_rate", "lt"),
    "heart_rate_lte": ("heart_rate", "lte"),
    "creatinine_gte": ("creatinine", "gte"),
    "creatinine_gt": ("creatinine", "gt"),
}

_CRITERION_OPERATOR_MAP = {
    "lt": "lt",
    "lte": "lte",
    "gt": "gt",
    "gte": "gte",
    "eq": "eq",
    "equals": "eq",
}

# Numeric patterns in free text (field, operator, value).
_EVIDENCE_PATTERNS: tuple[tuple[re.Pattern[str], str, str], ...] = (
    (re.compile(r"\b(?:e?gfr|estimated gfr)\s*(?:<|≤|<=)\s*(\d+(?:\.\d+)?)", re.I), "egfr", "lt"),
    (re.compile(r"\b(?:e?gfr|estimated gfr)\s*(?:>|≥|>=)\s*(\d+(?:\.\d+)?)", re.I), "egfr", "gt"),
    (re.compile(r"\b(?:crcl|creatinine clearance)\s*(?:<|≤|<=)\s*(\d+(?:\.\d+)?)", re.I), "crcl", "lt"),
    (re.compile(r"\bpotassium\s*(?:>|≥|>=)\s*(\d+(?:\.\d+)?)", re.I), "potassium", "gte"),
    (re.compile(r"\b(?:serum )?k\+?\s*(?:>|≥|>=)\s*(\d+(?:\.\d+)?)", re.I), "potassium", "gte"),
    (re.compile(r"\bheart rate\s*(?:<|≤|<=)\s*(\d+(?:\.\d+)?)", re.I), "heart_rate", "lt"),
    (re.compile(r"\bsystolic(?: blood pressure| bp)?\s*(?:<|≤|<=)\s*(\d+(?:\.\d+)?)", re.I), "systolic_bp", "lt"),
    (re.compile(r"\b(?:less than|below)\s*(\d+(?:\.\d+)?)\s*mL/min(?:/1\.73\s*m2)?", re.I), "egfr", "lt"),
)

_RENAL_REVIEW_CUE = re.compile(
    r"\b(renal function review|monitor renal|renal impairment|reduced egfr|egfr decline|"
    r"renal dysfunction|kidney function)\b",
    re.I,
)
_MONITORING_CUE = re.compile(
    r"\b(monitor (?:potassium|renal|electrolyte|serum creatinine)|lab monitoring)\b",
    re.I,
)


def _coerce_number(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _condition(field: str, operator: str, value: float | None = None) -> dict[str, Any]:
    item: dict[str, Any] = {"field": field, "operator": operator}
    if value is not None:
        item["value"] = value
    return item


def _map_criterion_operator(operator: str, field: str, *, safety_context: bool = True) -> str:
    op = _CRITERION_OPERATOR_MAP.get(operator.strip().lower(), operator.strip().lower())
    if safety_context and field in {"egfr", "crcl"} and op in {"lt", "lte"}:
        # Renal dose/safety gates should fire when lab is missing.
        return "missing_or_lt" if op == "lt" else "missing_or_lte"
    return op


def hold_if_to_condition_groups(hold_if: dict[str, Any] | None) -> list[list[dict[str, Any]]]:
    if not isinstance(hold_if, dict):
        return []
    groups: list[list[dict[str, Any]]] = []
    for key, raw_value in hold_if.items():
        mapping = _HOLD_IF_KEY_MAP.get(str(key).strip().lower())
        if not mapping:
            continue
        field, operator = mapping
        if isinstance(raw_value, bool):
            if raw_value:
                groups.append([_condition(field, "present")])
            continue
        value = _coerce_number(raw_value)
        if value is None:
            continue
        groups.append([_condition(field, operator, value)])
    return groups


def reduction_criteria_to_condition_groups(criteria: list[Any] | None) -> list[list[dict[str, Any]]]:
    groups: list[list[dict[str, Any]]] = []
    for item in criteria or []:
        if not isinstance(item, dict):
            continue
        field = str(item.get("field") or "").strip().lower()
        operator = str(item.get("operator") or "").strip().lower()
        if not field or not operator:
            continue
        if field not in EVALUATOR_FIELDS:
            # LLM-proposed field the runtime evaluator can't read (e.g. "age") —
            # would silently never fire, or worse, be treated as evaluable when
            # it isn't grounded in the evidence at all. Drop it here rather
            # than letting an unreviewable trigger reach the catalog.
            continue
        if operator == "between":
            low = _coerce_number(item.get("value_low"))
            high = _coerce_number(item.get("value_high"))
            if low is not None and high is not None:
                groups.append([_condition(field, "gte", low), _condition(field, "lte", high)])
            continue
        value = _coerce_number(item.get("value"))
        if value is None:
            continue
        mapped = _map_criterion_operator(operator, field)
        groups.append([_condition(field, mapped, value)])
    return groups


def crcl_threshold_to_condition_groups(
    threshold: Any,
    minimum: Any = None,
) -> list[list[dict[str, Any]]]:
    groups: list[list[dict[str, Any]]] = []
    value = _coerce_number(threshold)
    if value is not None:
        groups.append([_condition("crcl", "missing_or_lt", value)])
    min_value = _coerce_number(minimum)
    if min_value is not None:
        groups.append([_condition("crcl", "lt", min_value)])
    return groups


def evidence_to_condition_groups(text: str) -> list[list[dict[str, Any]]]:
    groups: list[list[dict[str, Any]]] = []
    seen: set[tuple[str, str, float]] = set()
    for pattern, field, operator in _EVIDENCE_PATTERNS:
        for match in pattern.finditer(text):
            value = _coerce_number(match.group(1))
            if value is None:
                continue
            mapped = _map_criterion_operator(operator, field)
            key = (field, mapped, value)
            if key in seen:
                continue
            seen.add(key)
            groups.append([_condition(field, mapped, value)])

    lowered = text.lower()
    if _RENAL_REVIEW_CUE.search(text) and not any(g[0].get("field") == "egfr" for g in groups if g):
        groups.append([_condition("egfr", "missing_or_lt", 60.0)])
    if _MONITORING_CUE.search(text):
        if "potassium" in lowered and not any(g[0].get("field") == "potassium" for g in groups if g):
            groups.append([_condition("potassium", "missing")])
        if any(token in lowered for token in ("renal", "egfr", "creatinine")) and not any(
            g[0].get("field") in {"egfr", "creatinine", "crcl"} for g in groups if g
        ):
            groups.append([_condition("egfr", "missing")])
    return groups


def related_observation_fields_from_groups(groups: list[list[dict[str, Any]]]) -> list[str]:
    fields: list[str] = []
    for group in groups:
        for cond in group:
            field = str(cond.get("field") or "").strip()
            if field and field not in fields and field != "always":
                fields.append(field)
    return fields


def build_trigger_from_claim(claim: dict[str, Any]) -> dict[str, Any] | None:
    """Return trigger dict with condition_groups, or None when no evaluable gate exists."""
    body = claim.get("rule_body") or {}
    existing = body.get("trigger") if isinstance(body.get("trigger"), dict) else None
    if existing and existing.get("condition_groups"):
        flat_ops = [
            str(item.get("operator") or "")
            for group in existing.get("condition_groups") or []
            for item in (group if isinstance(group, list) else [group])
            if isinstance(item, dict)
        ]
        if flat_ops and not all(op.lower() == "always" for op in flat_ops):
            return existing

    groups: list[list[dict[str, Any]]] = []
    groups.extend(hold_if_to_condition_groups(claim.get("hold_if")))
    groups.extend(reduction_criteria_to_condition_groups(claim.get("reduction_criteria")))
    groups.extend(crcl_threshold_to_condition_groups(claim.get("crcl_threshold"), claim.get("crcl_minimum")))

    if claim.get("renal_adjustment") and not any(
        g and g[0].get("field") in {"egfr", "crcl", "creatinine"} for g in groups
    ):
        groups.append([_condition("egfr", "missing_or_lt", 60.0)])

    haystack = " ".join(
        str(claim.get(key) or "")
        for key in ("evidence", "notes", "message", "monitoring", "lab_monitoring", "renal_adjustment")
    )
    for group in evidence_to_condition_groups(haystack):
        if group not in groups:
            groups.append(group)

    if not groups:
        return None
    return {"condition_groups": groups}


def build_severity_rules_from_claim(claim: dict[str, Any]) -> list[dict[str, Any]]:
    rules: list[dict[str, Any]] = []
    for group in (build_trigger_from_claim(claim) or {}).get("condition_groups") or []:
        for cond in group:
            field = cond.get("field")
            operator = cond.get("operator")
            value = cond.get("value")
            if field == "potassium" and operator in {"gte", "gt", "missing_or_lt"} and value is not None:
                try:
                    if float(value) >= 5.5:
                        rules.append({"field": field, "operator": "gte", "value": 5.5, "severity": "high"})
                except (TypeError, ValueError):
                    pass
            if field == "egfr" and operator in {"lt", "missing_or_lt"} and value is not None:
                try:
                    if float(value) <= 30:
                        rules.append({"field": field, "operator": "lt", "value": 30, "severity": "high"})
                except (TypeError, ValueError):
                    pass
    return rules
