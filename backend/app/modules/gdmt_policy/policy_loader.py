"""Refactored GDMT policy loader using shared RuleCache."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from app.core.rule_cache import RuleCache
from app.modules.datastores.gdmt_policies_postgres import read_approved_gdmt_policies

_MODULE_DIR = Path(__file__).resolve().parent


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


def _normalize_policy_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    policies = [_normalize_policy_row(row) for row in rows]
    return sorted(policies, key=lambda item: int(item.get("sort_order") or 0))


_CACHE = RuleCache(
    catalog_name="gdmt_policies",
    ttl_seconds_setting="gdmt_policy_cache_ttl_seconds",
    fallback_path=_MODULE_DIR / "rules" / "hf_gdmt_policy_v1.json",
    list_key="policies",
    db_loader=read_approved_gdmt_policies,
    default_version="hf_gdmt_policy_v1",
    postgres_source="postgres_approved_gdmt_policies",
    transform_rows=_normalize_policy_rows,
)


def invalidate_gdmt_policy_cache() -> None:
    _CACHE.invalidate()


def load_gdmt_policy_bundle() -> dict[str, Any]:
    return _CACHE.load_bundle()


def load_executable_gdmt_policies() -> list[dict[str, Any]]:
    return _CACHE.load_items()


def gdmt_policy_version() -> str:
    return _CACHE.version()
