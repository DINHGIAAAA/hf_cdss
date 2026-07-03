"""Load approved GDMT recommendation policies from Postgres with JSON fallback."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from app.core.config import settings
from app.modules.datastores.gdmt_policies_postgres import read_approved_gdmt_policies

logger = logging.getLogger(__name__)

_CACHE_TIMESTAMP: datetime | None = None
_cached_bundle: dict[str, Any] | None = None
_FALLBACK_PATH = Path(__file__).resolve().parent / "rules" / "hf_gdmt_policy_v1.json"


def _cache_ttl_seconds() -> int:
    return int(getattr(settings, "gdmt_policy_cache_ttl_seconds", 300))


def invalidate_gdmt_policy_cache() -> None:
    global _CACHE_TIMESTAMP, _cached_bundle
    _CACHE_TIMESTAMP = None
    _cached_bundle = None


def _load_fallback_bundle() -> dict[str, Any]:
    if not _FALLBACK_PATH.is_file():
        return {"version": "hf_gdmt_policy_v1", "source": "bundled_fallback", "policies": []}
    payload = json.loads(_FALLBACK_PATH.read_text(encoding="utf-8"))
    return {
        "version": payload.get("version", "hf_gdmt_policy_v1"),
        "source": payload.get("source", "bundled_fallback"),
        "policies": list(payload.get("policies") or []),
    }


def _should_refresh_cache() -> bool:
    global _CACHE_TIMESTAMP
    if _CACHE_TIMESTAMP is None or _cached_bundle is None:
        return True
    return datetime.now() - _CACHE_TIMESTAMP > timedelta(seconds=_cache_ttl_seconds())


def _normalize_policy_row(row: dict[str, Any]) -> dict[str, Any]:
    body = dict(row.get("policy_body") or {})
    if row.get("med_detection_terms"):
        body.setdefault("med_detection_terms", row.get("med_detection_terms"))
    if row.get("warning_targets"):
        body.setdefault("warning_targets", row.get("warning_targets"))
    if row.get("aliases"):
        body.setdefault("aliases", row.get("aliases"))
    return {
        "gdmt_policy_id": row.get("gdmt_policy_id"),
        "drug_class_key": row.get("drug_class_key"),
        "display_label": row.get("display_label"),
        "sort_order": row.get("sort_order", 0),
        "policy_body": body,
        "evidence_ref": row.get("evidence_ref"),
    }


def load_gdmt_policy_bundle() -> dict[str, Any]:
    global _CACHE_TIMESTAMP, _cached_bundle
    if not _should_refresh_cache() and _cached_bundle is not None:
        return _cached_bundle

    try:
        rows = read_approved_gdmt_policies()
        if rows:
            policies = [_normalize_policy_row(row) for row in rows]
            policies.sort(key=lambda item: int(item.get("sort_order") or 0))
            bundle = {
                "version": f"postgres_approved_{len(policies)}",
                "source": "postgres_approved_gdmt_policies",
                "policies": policies,
            }
            _cached_bundle = bundle
            _CACHE_TIMESTAMP = datetime.now()
            return bundle
    except Exception as exc:
        logger.error("Could not load GDMT policies from Postgres: %s", exc, exc_info=True)
        if _cached_bundle is not None:
            return _cached_bundle

    fallback = _load_fallback_bundle()
    logger.warning(
        "Serving bundled fallback GDMT policies (%s policies)",
        len(fallback.get("policies") or []),
    )
    _cached_bundle = fallback
    _CACHE_TIMESTAMP = datetime.now()
    return fallback


def load_executable_gdmt_policies() -> list[dict[str, Any]]:
    policies = list(load_gdmt_policy_bundle().get("policies") or [])
    return sorted(policies, key=lambda item: int(item.get("sort_order") or 0))


def gdmt_policy_version() -> str:
    return str(load_gdmt_policy_bundle().get("version") or "unknown")
