"""Refactored dose rule loader using shared RuleCache."""

from __future__ import annotations

from typing import Any

from app.core.config import settings
from app.core.rule_cache import RuleCache
from app.modules.datastores.postgres import read_approved_dose_rules
from app.modules.dose_calculator.dose_rules_paths import (
    expected_bundle_version_label,
    resolve_dose_rules_bundle_path,
)
from app.modules.dose_calculator.rule_validation import validate_bundle_payload, validate_runtime_bundle


def _validate_dose_bundle(bundle: dict[str, Any]) -> dict[str, Any]:
    if bundle.get("source") == "postgres_approved_dose_rules":
        return validate_runtime_bundle(bundle)

    payload = {
        "version": bundle.get("version") or expected_bundle_version_label(),
        "source": bundle.get("source"),
        "rules": list(bundle.get("rules") or []),
    }
    expected_version = None if (getattr(settings, "dose_rules_bundle_path", None) or "").strip() else expected_bundle_version_label()
    validated = validate_bundle_payload(
        payload,
        expected_version=expected_version,
        source_label="bundled_fallback",
    )
    return {**bundle, "rules": validated.get("rules") or []}


def _rows_to_rules(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rules: list[dict[str, Any]] = []
    for row in rows:
        body = dict(row.get("rule_body") or {})
        body["rule_id"] = row.get("dose_rule_id") or body.get("rule_id")
        body["drug_keys"] = row.get("drug_keys") or body.get("drug_keys") or []
        body["drug_class"] = row.get("drug_class") or body.get("drug_class")
        body["calculation_type"] = row.get("calculation_type") or body.get("calculation_type")
        body["_db_version"] = row.get("version")
        body["_db_status"] = row.get("status")
        body["_bundle_version"] = (row.get("metadata") or {}).get("bundle_version")
        rules.append(body)
    return rules


_CACHE = RuleCache(
    catalog_name="dose_rules",
    ttl_seconds_setting="dose_rules_cache_ttl_seconds",
    fallback_path_resolver=resolve_dose_rules_bundle_path,
    list_key="rules",
    db_loader=read_approved_dose_rules,
    default_version=expected_bundle_version_label(),
    postgres_source="postgres_approved_dose_rules",
    transform_rows=_rows_to_rules,
    validate_bundle=_validate_dose_bundle,
    enabled=lambda: bool(getattr(settings, "dose_calculator_enabled", True)),
    disabled_bundle={"version": "disabled", "source": "feature_flag", "rules": []},
)


def invalidate_dose_rules_cache() -> None:
    _CACHE.invalidate()


def load_dose_rules_bundle() -> dict[str, Any]:
    return _CACHE.load_bundle()


def _load_fallback_bundle() -> dict[str, Any]:
    """Load bundled JSON fallback only (used by tests and legacy callers)."""
    return _CACHE._load_fallback_bundle()


def load_executable_dose_rules() -> list[dict[str, Any]]:
    return _CACHE.load_items()


def dose_rules_version() -> str:
    return _CACHE.version()
