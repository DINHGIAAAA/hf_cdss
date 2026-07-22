"""Embedding-based near-duplicate removal."""

from __future__ import annotations

import logging
from collections import defaultdict
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


def _document_scope_key(record: dict) -> str:
    """Scope near-duplicate removal to one source document.

    FDA labels share boilerplate across drugs; cross-document MinHash/embedding
    dedupe previously dropped ~140 drug labels from chunks.
    """
    metadata = record.get("metadata") or {}
    return str(
        record.get("document_id")
        or metadata.get("source_document_id")
        or metadata.get("source_id")
        or ""
    )


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
    kept_scopes: dict[str, str] = {}

    for record in records:
        record_id = record.get("chunk_id") or record.get("id") or str(id(record))
        text = _text_from_record(record, text_field)
        signature = minhash_signature(text, num_perm=num_perm)
        scope = _document_scope_key(record)

        if not signature:
            kept.append(record)
            continue

        # Only compare against candidates from LSH buckets, not all kept records
        candidate_ids = candidates.get(record_id, set())
        duplicate = False

        for candidate_id in candidate_ids:
            if candidate_id not in kept_signatures:
                continue
            # Never collapse content from different documents (e.g. two SPLs).
            if scope and kept_scopes.get(candidate_id) and kept_scopes[candidate_id] != scope:
                continue
            if minhash_jaccard(signature, kept_signatures[candidate_id]) >= threshold:
                duplicate = True
                break

        if duplicate:
            continue

        kept.append(record)
        kept_signatures[record_id] = signature
        kept_scopes[record_id] = scope

    return kept


def _dedupe_by_embedding_within(
    records: list[dict],
    *,
    text_field: str,
    threshold: float,
) -> list[dict]:
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


def dedupe_by_embedding(
    records: list[dict],
    *,
    text_field: str = "text",
    threshold: float,
    id_field: str,
) -> list[dict]:
    if len(records) <= 1:
        return records

    # Deduplicate within each document so shared label boilerplate cannot
    # erase another drug's sections/chunks.
    by_scope: dict[str, list[dict]] = defaultdict(list)
    order: list[str] = []
    for record in records:
        scope = _document_scope_key(record) or "__none__"
        if scope not in by_scope:
            order.append(scope)
        by_scope[scope].append(record)

    output: list[dict] = []
    for scope in order:
        group = by_scope[scope]
        working = group
        if getattr(config, "MINHASH_DEDUP_ENABLED", True):
            minhash_threshold = min(0.98, threshold + 0.02)
            working = _dedupe_by_minhash(group, text_field=text_field, threshold=minhash_threshold)
            if len(working) <= 1:
                output.extend(working)
                continue

        if config.EMBEDDING_DEDUP_ENABLED:
            working = _dedupe_by_embedding_within(
                working,
                text_field=text_field,
                threshold=threshold,
            )
        output.extend(working)
    return output


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
