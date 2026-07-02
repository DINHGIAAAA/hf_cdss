"""Embedding-based near-duplicate removal."""

from __future__ import annotations

import logging
from typing import Callable

from scraper.semantic import config
from scraper.semantic.embeddings import cosine_similarity, embed_texts

logger = logging.getLogger(__name__)


def _text_from_record(record: dict, field: str) -> str:
    value = record.get(field)
    if isinstance(value, str):
        return value.strip()
    metadata = record.get("metadata") or {}
    if field in metadata and isinstance(metadata[field], str):
        return metadata[field].strip()
    return ""


def dedupe_by_embedding(
    records: list[dict],
    *,
    text_field: str = "text",
    threshold: float,
    id_field: str,
) -> list[dict]:
    if len(records) <= 1:
        return records

    texts = [_text_from_record(record, text_field) for record in records]
    try:
        vectors = embed_texts(texts)
    except Exception as exc:
        logger.warning("Embedding dedupe skipped: %s", exc)
        return records

    kept: list[dict] = []
    kept_vectors: list[list[float]] = []
    for record, vector in zip(records, vectors):
        if not vector:
            kept.append(record)
            continue
        duplicate = False
        for kept_vector in kept_vectors:
            if cosine_similarity(vector, kept_vector) >= threshold:
                duplicate = True
                break
        if duplicate:
            continue
        kept.append(record)
        kept_vectors.append(vector)
    return kept


def dedupe_claims(records: list[dict]) -> list[dict]:
    return dedupe_by_embedding(
        records,
        text_field="evidence",
        threshold=config.CLAIM_DEDUP_THRESHOLD,
        id_field="claim_id",
    )


def dedupe_chunks(records: list[dict]) -> list[dict]:
    return dedupe_by_embedding(
        records,
        text_field="text",
        threshold=config.CHUNK_DEDUP_THRESHOLD,
        id_field="chunk_id",
    )
