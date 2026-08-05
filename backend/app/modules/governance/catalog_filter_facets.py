"""Distinct filter values per governance catalog, with cross-field narrowing."""

from __future__ import annotations

from typing import Any, Callable

from app.modules.datastores.postgres import postgres_pool

ConditionBuilder = Callable[[dict[str, Any], str | None], tuple[list[str], list[Any]]]


def _eq(column: str, value: str, conditions: list[str], params: list[Any]) -> None:
    conditions.append(f"{column} = %s")
    params.append(value)


def _ilike(column: str, value: str, conditions: list[str], params: list[Any]) -> None:
    conditions.append(f"{column} ILIKE %s")
    params.append(f"%{value}%")


def _status_filter(filters: dict[str, Any], conditions: list[str], params: list[Any]) -> None:
    status = filters.get("status")
    if status:
        conditions.append("status = %s")
        params.append(status)


def _build_dose_rules(filters: dict[str, Any], exclude: str | None) -> tuple[list[str], list[Any]]:
    conditions: list[str] = []
    params: list[Any] = []
    _status_filter(filters, conditions, params)
    if exclude != "drug_class" and filters.get("drug_class"):
        _eq("drug_class", str(filters["drug_class"]), conditions, params)
    if exclude != "calculation_type" and filters.get("calculation_type"):
        _eq("calculation_type", str(filters["calculation_type"]), conditions, params)
    if exclude != "safety_tier" and filters.get("safety_tier"):
        _eq("safety_tier", str(filters["safety_tier"]), conditions, params)
    if exclude != "q" and filters.get("q"):
        _ilike("dose_rule_id", str(filters["q"]), conditions, params)
    return conditions, params


def _build_gdmt_policies(filters: dict[str, Any], exclude: str | None) -> tuple[list[str], list[Any]]:
    conditions: list[str] = []
    params: list[Any] = []
    _status_filter(filters, conditions, params)
    if exclude != "drug_class_key" and filters.get("drug_class_key"):
        _eq("drug_class_key", str(filters["drug_class_key"]), conditions, params)
    if exclude != "safety_tier" and filters.get("safety_tier"):
        _eq("safety_tier", str(filters["safety_tier"]), conditions, params)
    if exclude != "q" and filters.get("q"):
        q = str(filters["q"])
        conditions.append("(gdmt_policy_id ILIKE %s OR display_label ILIKE %s)")
        params.extend([f"%{q}%", f"%{q}%"])
    return conditions, params


def _build_interaction_rules(filters: dict[str, Any], exclude: str | None) -> tuple[list[str], list[Any]]:
    conditions: list[str] = []
    params: list[Any] = []
    _status_filter(filters, conditions, params)
    if exclude != "severity" and filters.get("severity"):
        _eq("severity", str(filters["severity"]), conditions, params)
    if exclude != "target" and filters.get("target"):
        _eq("target", str(filters["target"]), conditions, params)
    if exclude != "safety_tier" and filters.get("safety_tier"):
        _eq("safety_tier", str(filters["safety_tier"]), conditions, params)
    if exclude != "extraction_method" and filters.get("extraction_method"):
        conditions.append("metadata->>'extraction_method' = %s")
        params.append(str(filters["extraction_method"]))
    if exclude != "q" and filters.get("q"):
        _ilike("interaction_rule_id", str(filters["q"]), conditions, params)
    return conditions, params


def _build_dose_safety_warnings(filters: dict[str, Any], exclude: str | None) -> tuple[list[str], list[Any]]:
    conditions: list[str] = []
    params: list[Any] = []
    _status_filter(filters, conditions, params)
    if exclude != "target" and filters.get("target"):
        _eq("target", str(filters["target"]), conditions, params)
    if exclude != "default_severity" and filters.get("default_severity"):
        _eq("default_severity", str(filters["default_severity"]), conditions, params)
    if exclude != "safety_tier" and filters.get("safety_tier"):
        _eq("safety_tier", str(filters["safety_tier"]), conditions, params)
    if exclude != "q" and filters.get("q"):
        q = str(filters["q"])
        conditions.append("(dose_safety_warning_id ILIKE %s OR target ILIKE %s)")
        params.extend([f"%{q}%", f"%{q}%"])
    return conditions, params


def _build_constraint_rules(filters: dict[str, Any], exclude: str | None) -> tuple[list[str], list[Any]]:
    conditions: list[str] = []
    params: list[Any] = []
    _status_filter(filters, conditions, params)
    if exclude != "target_drug_class" and filters.get("target_drug_class"):
        _eq("target_drug_class", str(filters["target_drug_class"]), conditions, params)
    if exclude != "action" and filters.get("action"):
        _eq("action", str(filters["action"]), conditions, params)
    if exclude != "safety_tier" and filters.get("safety_tier"):
        conditions.append("metadata->>'safety_tier' = %s")
        params.append(str(filters["safety_tier"]))
    if exclude != "needs_condition" and filters.get("needs_condition") in ("true", "false"):
        if filters["needs_condition"] == "true":
            conditions.append("(metadata->>'needs_condition') = 'true'")
        else:
            conditions.append("(metadata->>'needs_condition') IS DISTINCT FROM 'true'")
    if exclude != "q" and filters.get("q"):
        _ilike("constraint_id", str(filters["q"]), conditions, params)
    return conditions, params


CATALOG_FACET_SPECS: dict[str, dict[str, Any]] = {
    "dose-rules": {
        "table": "dose_rules",
        "fields": {
            "drug_class": "drug_class",
            "calculation_type": "calculation_type",
            "safety_tier": "safety_tier",
        },
        "build": _build_dose_rules,
    },
    "gdmt-policies": {
        "table": "gdmt_policies",
        "fields": {
            "drug_class_key": "drug_class_key",
            "safety_tier": "safety_tier",
        },
        "build": _build_gdmt_policies,
    },
    "interaction-rules": {
        "table": "interaction_rules",
        "fields": {
            "severity": "severity",
            "target": "target",
            "safety_tier": "safety_tier",
            "extraction_method": "metadata->>'extraction_method'",
        },
        "build": _build_interaction_rules,
    },
    "dose-safety-warnings": {
        "table": "dose_safety_warnings",
        "fields": {
            "target": "target",
            "default_severity": "default_severity",
            "safety_tier": "safety_tier",
        },
        "build": _build_dose_safety_warnings,
    },
    "constraints": {
        "table": "constraint_rules",
        "fields": {
            "target_drug_class": "target_drug_class",
            "action": "action",
        },
        "build": _build_constraint_rules,
    },
}


def list_catalog_filter_facets(catalog_id: str, filters: dict[str, Any]) -> dict[str, list[str]]:
    spec = CATALOG_FACET_SPECS.get(catalog_id)
    if not spec:
        return {}
    table = spec["table"]
    fields: dict[str, str] = spec["fields"]
    build: ConditionBuilder = spec["build"]
    result: dict[str, list[str]] = {}
    with postgres_pool().connection() as connection:
        with connection.cursor() as cursor:
            for field_key, column_expr in fields.items():
                conditions, params = build(filters, exclude=field_key)
                conditions.append(f"{column_expr} IS NOT NULL")
                conditions.append(f"TRIM({column_expr}::text) <> ''")
                where = f"WHERE {' AND '.join(conditions)}"
                cursor.execute(
                    f"SELECT DISTINCT {column_expr} FROM {table} {where} ORDER BY 1",  # noqa: S608
                    tuple(params),
                )
                result[field_key] = [str(row[0]) for row in cursor.fetchall() if row[0] is not None]
    return result
