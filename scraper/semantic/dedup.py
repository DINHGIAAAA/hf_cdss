"""Embedding-based near-duplicate removal."""

from __future__ import annotations

import logging
from typing import Any

from scraper.semantic import config
from scraper.semantic.embeddings import cosine_similarity, embed_texts
from scraper.semantic.minhash import (
    minhash_candidate_buckets,
    minhash_jaccard,
    minhash_signature,
)

logger = logging.getLogger(__name__)


def _text_from_record(record: dict, field: str) -> str:
    value = record.get(field)
    if isinstance(value, str):
        return value.strip()
    metadata = record.get("metadata") or {}
    if field in metadata and isinstance(metadata[field], str):
        return metadata[field].strip()
    return ""


def _dedupe_by_minhash(
    records: list[dict],
    *,
    text_field: str,
    threshold: float,
) -> list[dict]:
    """Deduplicate using LSH banding for O(n) average time.

    Instead of O(n²) pair-wise comparison, uses Locality-Sensitive Hashing
    to find candidate duplicates in O(1) per record, then only compares
    within candidate buckets.
    """
    if len(records) <= 1:
        return records

    num_bands = getattr(config, "MINHASH_NUM_BANDS", 8)
    num_perm = config.MINHASH_NUM_PERM

    # Build LSH candidate buckets: O(n) instead of O(n²)
    candidates = minhash_candidate_buckets(
        records,
        text_field=text_field,
        num_perm=num_perm,
        num_bands=num_bands,
    )

    kept: list[dict] = []
    kept_signatures: dict[str, tuple[int, ...]] = {}

    for record in records:
        record_id = record.get("chunk_id") or record.get("id") or str(id(record))
        text = _text_from_record(record, text_field)
        signature = minhash_signature(text, num_perm=num_perm)

        if not signature:
            kept.append(record)
            continue

        # Only compare against candidates from LSH buckets, not all kept records
        candidate_ids = candidates.get(record_id, set())
        duplicate = False

        for candidate_id in candidate_ids:
            if candidate_id in kept_signatures:
                if minhash_jaccard(signature, kept_signatures[candidate_id]) >= threshold:
                    duplicate = True
                    break

        if duplicate:
            continue

        kept.append(record)
        kept_signatures[record_id] = signature

    return kept


def dedupe_by_embedding(
    records: list[dict],
    *,
    text_field: str = "text",
    threshold: float,
    id_field: str,
) -> list[dict]:
    if len(records) <= 1:
        return records

    working = records
    if getattr(config, "MINHASH_DEDUP_ENABLED", True):
        minhash_threshold = min(0.98, threshold + 0.02)
        working = _dedupe_by_minhash(records, text_field=text_field, threshold=minhash_threshold)
        if len(working) <= 1:
            return working

    if not config.EMBEDDING_DEDUP_ENABLED:
        return working

    texts = [_text_from_record(record, text_field) for record in working]
    try:
        vectors = embed_texts(texts)
    except Exception as exc:
        logger.warning("Embedding dedupe skipped: %s", exc)
        return working

    kept: list[dict] = []
    kept_vectors: list[list[float]] = []
    for record, vector in zip(working, vectors):
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
