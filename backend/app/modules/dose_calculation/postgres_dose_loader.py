"""Load approved dose_rules from Postgres for runtime dose calculation."""

from __future__ import annotations

from typing import Any

from app.core.rule_cache import RuleCache
from app.modules.datastores.postgres import read_approved_dose_rules
from app.modules.dose_calculation.governance_drug_adapter import approved_dose_rules_to_tables

_CACHE = RuleCache(
    catalog_name="dose_rules",
    ttl_seconds_setting="dose_rules_cache_ttl_seconds",
    fallback_path=None,
    list_key="rules",
    db_loader=read_approved_dose_rules,
    default_version="hf_dose_rules_v1",
    postgres_source="postgres_approved_dose_rules",
)


def invalidate_postgres_dose_rules_cache() -> None:
    _CACHE.invalidate()


def load_tables_from_postgres() -> dict[str, Any]:
    bundle = _CACHE.load_bundle()
    rows = list(bundle.get("rules") or [])
    version = str(bundle.get("version") or "postgres_approved_dose_rules")
    source = str(bundle.get("source") or "postgres_approved_dose_rules")
    return approved_dose_rules_to_tables(rows, version=version, source=source)
