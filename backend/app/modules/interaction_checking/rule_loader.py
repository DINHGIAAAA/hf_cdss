"""Refactored rule loaders using shared RuleCache."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from app.core.config import settings
from app.core.rule_cache import RuleCache
from app.modules.datastores.interaction_rules_postgres import read_approved_interaction_rules

_MODULE_DIR = Path(__file__).resolve().parent

_CACHE = RuleCache(
    catalog_name="interaction_rules",
    ttl_seconds_setting="interaction_rules_cache_ttl_seconds",
    fallback_path=_MODULE_DIR / "rules" / "hf_interaction_rules_v1.json",
    list_key="rules",
    db_loader=read_approved_interaction_rules,
    default_version="hf_interaction_rules_v1",
    postgres_source="postgres_approved_interaction_rules",
)


def invalidate_interaction_rules_cache() -> None:
    _CACHE.invalidate()


def load_interaction_rules_bundle() -> dict[str, Any]:
    return _CACHE.load_bundle()


def load_executable_interaction_rules() -> list[dict[str, Any]]:
    return _CACHE.load_items()


def interaction_rules_version() -> str:
    return _CACHE.version()
