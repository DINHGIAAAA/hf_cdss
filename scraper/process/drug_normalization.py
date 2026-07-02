"""Shared drug alias resolution for the ingestion pipeline."""

from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path

from scraper.paths import data_root


def _normalize_token(value: str) -> str:
    return re.sub(r"[^a-z0-9+]+", " ", (value or "").lower()).strip()


@lru_cache(maxsize=1)
def _alias_index() -> dict[str, str]:
    path = data_root() / "config" / "drug_aliases.json"
    if not path.exists():
        return {}
    catalog = json.loads(path.read_text(encoding="utf-8"))
    index: dict[str, str] = {}
    for key, entry in catalog.items():
        pipeline_id = entry.get("pipeline_id") or key
        aliases = {pipeline_id, key, entry.get("display_name", "")}
        aliases.update(entry.get("aliases") or [])
        for alias in aliases:
            normalized = _normalize_token(str(alias))
            if normalized:
                index[normalized] = pipeline_id
    return index


def resolve_pipeline_drug_id(value: str | None) -> str | None:
    if not value:
        return None
    normalized = _normalize_token(value)
    if normalized in _alias_index():
        return _alias_index()[normalized]
    for alias, pipeline_id in _alias_index().items():
        if len(alias) >= 4 and re.search(rf"(?<![a-z0-9]){re.escape(alias)}(?![a-z0-9])", normalized):
            return pipeline_id
    return normalized.replace(" ", "_")
