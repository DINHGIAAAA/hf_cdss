"""Structured field diff for governance catalog versions."""

from __future__ import annotations

import json
from typing import Any, Literal

ChangeType = Literal["added", "removed", "modified", "unchanged"]


def _normalize(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _normalize(value[key]) for key in sorted(value)}
    if isinstance(value, list):
        return [_normalize(item) for item in value]
    return value


def _serialize(value: Any) -> str:
    return json.dumps(_normalize(value), sort_keys=True, default=str)


def diff_values(before: Any, after: Any) -> ChangeType:
    if before is None and after is None:
        return "unchanged"
    if before is None:
        return "added"
    if after is None:
        return "removed"
    if _serialize(before) == _serialize(after):
        return "unchanged"
    return "modified"


def diff_field_map(
    before: dict[str, Any],
    after: dict[str, Any],
    fields: list[str],
) -> list[dict[str, Any]]:
    changes: list[dict[str, Any]] = []
    for field in fields:
        change_type = diff_values(before.get(field), after.get(field))
        if change_type == "unchanged":
            continue
        changes.append(
            {
                "path": field,
                "change_type": change_type,
                "before": before.get(field),
                "after": after.get(field),
            }
        )
    return changes


CONSTRAINT_DIFF_FIELDS = [
    "action",
    "reason",
    "target_drug_class",
    "risk_names",
    "severity_any",
    "evidence_ref",
    "clinical_sources",
    "metadata",
]

DOSE_DIFF_FIELDS = [
    "calculation_type",
    "drug_class",
    "drug_keys",
    "rule_body",
    "evidence_ref",
    "safety_tier",
    "clinical_sources",
    "metadata",
]

INTERACTION_DIFF_FIELDS = [
    "drug_set_a",
    "drug_set_b",
    "severity",
    "target",
    "rule_body",
    "evidence_ref",
    "safety_tier",
    "clinical_sources",
    "metadata",
]


def constraint_diff_payload(rule: dict[str, Any]) -> dict[str, Any]:
    return {field: rule.get(field) for field in CONSTRAINT_DIFF_FIELDS}


def dose_diff_payload(rule: dict[str, Any]) -> dict[str, Any]:
    return {field: rule.get(field) for field in DOSE_DIFF_FIELDS}


GDMT_DIFF_FIELDS = [
    "drug_class_key",
    "display_label",
    "sort_order",
    "policy_body",
    "evidence_ref",
    "safety_tier",
    "clinical_sources",
    "metadata",
]


def interaction_diff_payload(rule: dict[str, Any]) -> dict[str, Any]:
    return {field: rule.get(field) for field in INTERACTION_DIFF_FIELDS}


def gdmt_diff_payload(policy: dict[str, Any]) -> dict[str, Any]:
    return {field: policy.get(field) for field in GDMT_DIFF_FIELDS}


DOSE_SAFETY_DIFF_FIELDS = [
    "drug_keys",
    "target",
    "default_severity",
    "rule_body",
    "evidence_ref",
    "safety_tier",
    "clinical_sources",
    "metadata",
]


def dose_safety_diff_payload(warning: dict[str, Any]) -> dict[str, Any]:
    return {field: warning.get(field) for field in DOSE_SAFETY_DIFF_FIELDS}
