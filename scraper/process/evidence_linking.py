"""Resolve ingestion chunk IDs for claims and pipeline rules."""

from __future__ import annotations

import re
from typing import Any

from scraper.io.jsonl import read_jsonl


def _normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", (value or "").lower()).strip()


def _overlap_score(left: str, right: str) -> float:
    left_norm = _normalize_text(left)
    right_norm = _normalize_text(right)
    if not left_norm or not right_norm:
        return 0.0
    if left_norm in right_norm or right_norm in left_norm:
        shorter = min(len(left_norm), len(right_norm))
        longer = max(len(left_norm), len(right_norm))
        return shorter / longer
    left_tokens = set(left_norm.split())
    right_tokens = set(right_norm.split())
    if not left_tokens or not right_tokens:
        return 0.0
    return len(left_tokens & right_tokens) / len(left_tokens | right_tokens)


def find_chunk_for_claim(claim: dict[str, Any], chunks: list[dict[str, Any]]) -> dict[str, Any] | None:
    evidence = claim.get("evidence") or claim.get("claim") or ""
    document_id = claim.get("document_id")
    section = claim.get("source_section")
    if not evidence:
        return None

    best: tuple[float, dict[str, Any]] | None = None
    for chunk in chunks:
        score = 0.0
        if document_id and chunk.get("document_id") == document_id:
            score += 0.35
        if section and chunk.get("section") == section:
            score += 0.2
        score += _overlap_score(evidence, chunk.get("text", "")) * 0.45
        if score <= 0:
            continue
        if best is None or score > best[0]:
            best = (score, chunk)
    if best and best[0] >= 0.35:
        return best[1]
    return None


def resolve_chunk_for_rule(rule: dict[str, Any], chunks: list[dict[str, Any]]) -> dict[str, Any] | None:
    for source_ref in rule.get("source_refs") or []:
        if not isinstance(source_ref, dict):
            continue
        chunk = find_chunk_for_claim(source_ref, chunks)
        if chunk:
            return chunk
    return None


def chunk_evidence_ref(chunk: dict[str, Any]) -> str:
    return str(chunk.get("chunk_id") or "")


def chunk_source_locator(chunk: dict[str, Any]) -> str | None:
    metadata = chunk.get("metadata") or {}
    provenance = metadata.get("provenance") or {}
    return (
        metadata.get("source_locator")
        or provenance.get("source_locator")
        or metadata.get("source_url")
    )
