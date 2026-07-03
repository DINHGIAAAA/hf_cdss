"""Load approved dose safety warnings from Postgres with JSON fallback."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from app.core.config import settings
from app.modules.datastores.dose_safety_warnings_postgres import read_approved_dose_safety_warnings

logger = logging.getLogger(__name__)

_CACHE_TIMESTAMP: datetime | None = None
_cached_bundle: dict[str, Any] | None = None
_FALLBACK_PATH = Path(__file__).resolve().parent / "rules" / "hf_dose_safety_warnings_v1.json"


def _cache_ttl_seconds() -> int:
    return int(getattr(settings, "dose_safety_warnings_cache_ttl_seconds", 300))


def invalidate_dose_safety_warnings_cache() -> None:
    global _CACHE_TIMESTAMP, _cached_bundle
    _CACHE_TIMESTAMP = None
    _cached_bundle = None


def _load_fallback_bundle() -> dict[str, Any]:
    if not _FALLBACK_PATH.is_file():
        return {"version": "hf_dose_safety_warnings_v1", "source": "bundled_fallback", "warnings": []}
    payload = json.loads(_FALLBACK_PATH.read_text(encoding="utf-8"))
    return {
        "version": payload.get("version", "hf_dose_safety_warnings_v1"),
        "source": payload.get("source", "bundled_fallback"),
        "warnings": list(payload.get("warnings") or []),
    }


def _should_refresh_cache() -> bool:
    global _CACHE_TIMESTAMP
    if _CACHE_TIMESTAMP is None or _cached_bundle is None:
        return True
    return datetime.now() - _CACHE_TIMESTAMP > timedelta(seconds=_cache_ttl_seconds())


def load_dose_safety_warnings_bundle() -> dict[str, Any]:
    global _CACHE_TIMESTAMP, _cached_bundle
    if not _should_refresh_cache() and _cached_bundle is not None:
        return _cached_bundle

    try:
        rows = read_approved_dose_safety_warnings()
        if rows:
            bundle = {
                "version": f"postgres_approved_{len(rows)}",
                "source": "postgres_approved_dose_safety_warnings",
                "warnings": rows,
            }
            _cached_bundle = bundle
            _CACHE_TIMESTAMP = datetime.now()
            return bundle
    except Exception as exc:
        logger.error("Could not load dose safety warnings from Postgres: %s", exc, exc_info=True)
        if _cached_bundle is not None:
            return _cached_bundle

    fallback = _load_fallback_bundle()
    logger.warning(
        "Serving bundled fallback dose safety warnings (%s rules)",
        len(fallback.get("warnings") or []),
    )
    _cached_bundle = fallback
    _CACHE_TIMESTAMP = datetime.now()
    return fallback


def load_executable_dose_safety_warnings() -> list[dict[str, Any]]:
    return list(load_dose_safety_warnings_bundle().get("warnings") or [])


def dose_safety_warnings_version() -> str:
    return str(load_dose_safety_warnings_bundle().get("version") or "unknown")
