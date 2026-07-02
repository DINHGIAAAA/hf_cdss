"""Resolve brand names and free-text medication mentions to canonical pipeline drug IDs.

Alias catalog is loaded from drug_aliases.json and cached in-process. After updating that file,
call invalidate_drug_catalog_cache() or restart the backend worker.
"""

from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

from app.modules.datastores.common import DATA_ROOT

_REPO_DATA_ROOT = Path(__file__).resolve().parents[4] / "data" / "heart_failure"


def _aliases_path() -> Path:
    preferred = DATA_ROOT / "config" / "drug_aliases.json"
    if preferred.is_file():
        return preferred
    repo_fallback = _REPO_DATA_ROOT / "config" / "drug_aliases.json"
    return repo_fallback


ALIASES_PATH = _aliases_path()


def invalidate_drug_catalog_cache() -> None:
    """Clear cached alias catalog after drug_aliases.json changes (requires reload on running process)."""
    load_drug_catalog.cache_clear()
    _alias_index.cache_clear()
    global ALIASES_PATH
    ALIASES_PATH = _aliases_path()


def _normalize_token(value: str) -> str:
    return re.sub(r"[^a-z0-9+]+", " ", (value or "").lower()).strip()


@lru_cache(maxsize=1)
def load_drug_catalog() -> dict[str, dict[str, Any]]:
    if not ALIASES_PATH.exists():
        return {}
    return json.loads(ALIASES_PATH.read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def _alias_index() -> dict[str, str]:
    index: dict[str, str] = {}
    for canonical_key, entry in load_drug_catalog().items():
        pipeline_id = entry.get("pipeline_id") or canonical_key
        aliases = {pipeline_id, canonical_key, entry.get("display_name", "")}
        aliases.update(entry.get("aliases") or [])
        for alias in aliases:
            normalized = _normalize_token(str(alias))
            if normalized:
                index[normalized] = pipeline_id
    return index


def normalize_drug_name(value: str | None) -> str | None:
    if not value:
        return None
    normalized = _normalize_token(value)
    if not normalized:
        return None
    if normalized in _alias_index():
        return _alias_index()[normalized]

    for alias, pipeline_id in _alias_index().items():
        if len(alias) < 4:
            continue
        if re.search(rf"(?<![a-z0-9]){re.escape(alias)}(?![a-z0-9])", normalized):
            return pipeline_id
    return normalized.replace(" ", "_")


def resolve_pipeline_drug_id(value: str | None) -> str | None:
    return normalize_drug_name(value)


def gdmt_class_for_drug(value: str | None) -> str | None:
    pipeline_id = resolve_pipeline_drug_id(value)
    if not pipeline_id:
        return None
    for entry in load_drug_catalog().values():
        if entry.get("pipeline_id") == pipeline_id:
            return entry.get("gdmt_class")
    return None


def display_name_for_drug(value: str | None) -> str | None:
    pipeline_id = resolve_pipeline_drug_id(value)
    if not pipeline_id:
        return value
    for entry in load_drug_catalog().values():
        if entry.get("pipeline_id") == pipeline_id:
            return entry.get("display_name") or pipeline_id.replace("_", " ")
    return pipeline_id.replace("_", " ")


def expand_drug_search_terms(value: str | None) -> list[str]:
    pipeline_id = resolve_pipeline_drug_id(value)
    if not pipeline_id:
        return []
    terms = {pipeline_id, pipeline_id.replace("_", " ")}
    for entry in load_drug_catalog().values():
        if entry.get("pipeline_id") == pipeline_id:
            terms.add(str(entry.get("display_name") or ""))
            terms.update(str(alias) for alias in entry.get("aliases") or [])
    return sorted({term.lower() for term in terms if term})


def format_constraint_target(value: str | None) -> str | None:
    if not value:
        return None
    catalog = load_drug_catalog()
    if value in catalog:
        return str(catalog[value].get("display_name") or value)
    for entry in catalog.values():
        if entry.get("pipeline_id") == value:
            return str(entry.get("display_name") or value)
    resolved = resolve_pipeline_drug_id(value)
    if resolved and any(entry.get("pipeline_id") == resolved for entry in catalog.values()):
        return display_name_for_drug(resolved) or value
    return value


def medications_catalog_for_intake() -> dict[str, tuple[str, tuple[str, ...]]]:
    catalog: dict[str, tuple[str, tuple[str, ...]]] = {}
    for key, entry in load_drug_catalog().items():
        gdmt_class = entry.get("gdmt_class") or "other"
        display = entry.get("display_name") or key.replace("_", " ")
        aliases = tuple(dict.fromkeys([display, *(entry.get("aliases") or [])]))
        catalog[display] = (gdmt_class, aliases)
    return catalog
