"""Refactored dose rule loader using shared RuleCache."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from app.core.config import settings
from app.core.rule_cache import RuleCache
from app.modules.datastores.postgres import read_approved_dose_rules

_MODULE_DIR = Path(__file__).resolve().parent


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
        rules.append(body)
    return rules


_CACHE = RuleCache(
    catalog_name="dose_rules",
    ttl_seconds_setting="dose_rules_cache_ttl_seconds",
    fallback_path=_MODULE_DIR / "rules" / "hf_dose_rules_v1.json",
    list_key="rules",
    db_loader=read_approved_dose_rules,
    default_version="hf_dose_rules_v1",
    postgres_source="postgres_approved_dose_rules",
    transform_rows=_rows_to_rules,
    enabled=lambda: bool(getattr(settings, "dose_calculator_enabled", True)),
    disabled_bundle={"version": "disabled", "source": "feature_flag", "rules": []},
)


def invalidate_dose_rules_cache() -> None:
    _CACHE.invalidate()


def expire_dose_rules_cache() -> None:
    _CACHE.expire()


def load_dose_rules_bundle() -> dict[str, Any]:
    return _CACHE.load_bundle()


def load_executable_dose_rules() -> list[dict[str, Any]]:
    return _CACHE.load_items()


def dose_rules_version() -> str:
    return _CACHE.version()
