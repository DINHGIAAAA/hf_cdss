"""Load approved dose rules from Postgres with TTL cache and JSON fallback."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from app.core.config import settings
from app.modules.datastores.postgres import read_approved_dose_rules

logger = logging.getLogger(__name__)

_CACHE_TIMESTAMP: datetime | None = None
_cached_bundle: dict[str, Any] | None = None
_FALLBACK_RULES_PATH = Path(__file__).resolve().parent / "rules" / "hf_dose_rules_v1.json"


def _cache_ttl_seconds() -> int:
    return int(getattr(settings, "dose_rules_cache_ttl_seconds", 300))


def _should_refresh_cache() -> bool:
    global _CACHE_TIMESTAMP
    if _CACHE_TIMESTAMP is None or _cached_bundle is None:
        return True
    return datetime.now() - _CACHE_TIMESTAMP > timedelta(seconds=_cache_ttl_seconds())


def invalidate_dose_rules_cache() -> None:
    global _CACHE_TIMESTAMP, _cached_bundle
    _CACHE_TIMESTAMP = None
    _cached_bundle = None


def expire_dose_rules_cache() -> None:
    global _CACHE_TIMESTAMP
    if _CACHE_TIMESTAMP is not None:
        _CACHE_TIMESTAMP = datetime.now() - timedelta(seconds=_cache_ttl_seconds() + 1)


def _load_fallback_bundle() -> dict[str, Any]:
    if not _FALLBACK_RULES_PATH.is_file():
        return {"version": "hf_dose_rules_v1", "source": "bundled_fallback", "rules": []}
    payload = json.loads(_FALLBACK_RULES_PATH.read_text(encoding="utf-8"))
    return {
        "version": payload.get("version", "hf_dose_rules_v1"),
        "source": payload.get("source", "bundled_fallback"),
        "rules": list(payload.get("rules") or []),
    }


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


def load_dose_rules_bundle() -> dict[str, Any]:
    """Return approved dose rules bundle with version metadata."""
    global _CACHE_TIMESTAMP, _cached_bundle

    if not getattr(settings, "dose_calculator_enabled", True):
        return {"version": "disabled", "source": "feature_flag", "rules": []}

    if not _should_refresh_cache() and _cached_bundle is not None:
        return _cached_bundle

    try:
        rows = read_approved_dose_rules()
        if rows:
            bundle = {
                "version": f"postgres_approved_{len(rows)}",
                "source": "postgres_approved_dose_rules",
                "rules": _rows_to_rules(rows),
            }
            _cached_bundle = bundle
            _CACHE_TIMESTAMP = datetime.now()
            return bundle
    except Exception as exc:
        logger.error("Could not load dose rules from Postgres: %s", exc, exc_info=True)
        if _cached_bundle is not None:
            logger.warning("Serving stale approved dose-rule cache after database error")
            return _cached_bundle

    fallback = _load_fallback_bundle()
    logger.warning(
        "Serving bundled fallback dose rules (%s rules) because no approved Postgres rules are available",
        len(fallback.get("rules") or []),
    )
    _cached_bundle = fallback
    _CACHE_TIMESTAMP = datetime.now()
    return fallback


def load_executable_dose_rules() -> list[dict[str, Any]]:
    return list(load_dose_rules_bundle().get("rules") or [])


def dose_rules_version() -> str:
    return str(load_dose_rules_bundle().get("version") or "unknown")
