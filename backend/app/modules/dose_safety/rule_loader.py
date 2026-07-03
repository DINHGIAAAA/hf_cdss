"""Refactored dose safety warning loader using shared RuleCache."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from app.core.rule_cache import RuleCache
from app.modules.datastores.dose_safety_warnings_postgres import read_approved_dose_safety_warnings

_MODULE_DIR = Path(__file__).resolve().parent

_CACHE = RuleCache(
    catalog_name="dose_safety_warnings",
    ttl_seconds_setting="dose_safety_warnings_cache_ttl_seconds",
    fallback_path=_MODULE_DIR / "rules" / "hf_dose_safety_warnings_v1.json",
    list_key="warnings",
    db_loader=read_approved_dose_safety_warnings,
    default_version="hf_dose_safety_warnings_v1",
    postgres_source="postgres_approved_dose_safety_warnings",
)


def invalidate_dose_safety_warnings_cache() -> None:
    _CACHE.invalidate()


def load_dose_safety_warnings_bundle() -> dict[str, Any]:
    return _CACHE.load_bundle()


def load_executable_dose_safety_warnings() -> list[dict[str, Any]]:
    return _CACHE.load_items()


def dose_safety_warnings_version() -> str:
    return _CACHE.version()
