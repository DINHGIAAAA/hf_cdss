"""Load approved interaction rules from Postgres with JSON fallback."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from app.core.config import settings
from app.modules.datastores.interaction_rules_postgres import read_approved_interaction_rules

logger = logging.getLogger(__name__)

_CACHE_TIMESTAMP: datetime | None = None
_cached_bundle: dict[str, Any] | None = None
_FALLBACK_PATH = Path(__file__).resolve().parent / "rules" / "hf_interaction_rules_v1.json"


def _cache_ttl_seconds() -> int:
    return int(getattr(settings, "interaction_rules_cache_ttl_seconds", 300))


def invalidate_interaction_rules_cache() -> None:
    global _CACHE_TIMESTAMP, _cached_bundle
    _CACHE_TIMESTAMP = None
    _cached_bundle = None


def _load_fallback_bundle() -> dict[str, Any]:
    if not _FALLBACK_PATH.is_file():
        return {"version": "hf_interaction_rules_v1", "source": "bundled_fallback", "rules": []}
    payload = json.loads(_FALLBACK_PATH.read_text(encoding="utf-8"))
    return {
        "version": payload.get("version", "hf_interaction_rules_v1"),
        "source": payload.get("source", "bundled_fallback"),
        "rules": list(payload.get("rules") or []),
    }


def _should_refresh_cache() -> bool:
    global _CACHE_TIMESTAMP
    if _CACHE_TIMESTAMP is None or _cached_bundle is None:
        return True
    return datetime.now() - _CACHE_TIMESTAMP > timedelta(seconds=_cache_ttl_seconds())


def load_interaction_rules_bundle() -> dict[str, Any]:
    global _CACHE_TIMESTAMP, _cached_bundle
    if not _should_refresh_cache() and _cached_bundle is not None:
        return _cached_bundle

    try:
        rows = read_approved_interaction_rules()
        if rows:
            bundle = {
                "version": f"postgres_approved_{len(rows)}",
                "source": "postgres_approved_interaction_rules",
                "rules": rows,
            }
            _cached_bundle = bundle
            _CACHE_TIMESTAMP = datetime.now()
            return bundle
    except Exception as exc:
        logger.error("Could not load interaction rules from Postgres: %s", exc, exc_info=True)
        if _cached_bundle is not None:
            return _cached_bundle

    fallback = _load_fallback_bundle()
    logger.warning(
        "Serving bundled fallback interaction rules (%s rules)",
        len(fallback.get("rules") or []),
    )
    _cached_bundle = fallback
    _CACHE_TIMESTAMP = datetime.now()
    return fallback


def load_executable_interaction_rules() -> list[dict[str, Any]]:
    return list(load_interaction_rules_bundle().get("rules") or [])


def interaction_rules_version() -> str:
    return str(load_interaction_rules_bundle().get("version") or "unknown")
