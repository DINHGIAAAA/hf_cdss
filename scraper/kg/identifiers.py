"""Stable IDs for KG nodes derived from ingestion artifacts."""

from __future__ import annotations

import hashlib
import re
from typing import Any


def slug(value: str) -> str:
    value = re.sub(r"[^a-zA-Z0-9]+", "_", value or "").strip("_").lower()
    return value or "unknown"


def section_id(document_id: str, section: str | None) -> str:
    raw = f"{document_id}|{section or ''}"
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:12]


def section_id_for_record(record: dict[str, Any]) -> str:
    metadata = record.get("metadata") or {}
    return section_id(
        str(record.get("document_id") or metadata.get("document_id") or ""),
        record.get("section") or metadata.get("section"),
    )


def chunk_node_id(chunk_id: str) -> str:
    return f"chunk:{chunk_id}"


def section_node_id(section_id_value: str) -> str:
    return f"section:{section_id_value}"


def document_node_id(document_id: str) -> str:
    normalized = (document_id or "unknown").strip().lower().replace(" ", "_")
    return f"document:{normalized}"
