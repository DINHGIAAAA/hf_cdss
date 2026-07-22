"""Hybrid keyword + embedding section relevance filtering."""

from __future__ import annotations

import logging

from scraper.transform.extract_important_sections import (
    DRUG_SECTION_ALIASES,
    drug_matches,
    guideline_matches,
    mark_record,
    normalize,
)
from scraper.transform.table_sections import is_extracted_table_section
from scraper.semantic import config
from scraper.semantic.embeddings import embed_text, max_similarity_vector_to_prototypes, warmup_prototype_vectors
from scraper.semantic.topic_prototypes import DRUG_SECTION_PROTOTYPES, GUIDELINE_TOPIC_PROTOTYPES

logger = logging.getLogger(__name__)


def _semantic_drug_matches(record: dict) -> list[str]:
    section = normalize(record.get("section", ""))
    text = (record.get("text") or "")[:2000]
    haystack = f"{section}\n{text}".strip()
    if not haystack:
        return []

    try:
        haystack_vector = embed_text(haystack)
    except Exception as exc:  # noqa: BLE001 — keep pipeline moving on Ollama blips
        logger.warning("Semantic drug embed skipped for section=%r: %s", section[:80], exc)
        return []

    matches: list[str] = []
    for canonical, prototypes in DRUG_SECTION_PROTOTYPES.items():
        aliases = DRUG_SECTION_ALIASES.get(canonical, {canonical})
        if section in aliases:
            matches.append(canonical)
            continue
        score = max_similarity_vector_to_prototypes(haystack_vector, prototypes)
        if score >= config.SECTION_SIMILARITY_THRESHOLD:
            matches.append(canonical)
    return matches


def _semantic_guideline_matches(record: dict) -> list[str]:
    haystack = f"{record.get('section', '')}\n{record.get('text', '')}"[:2000].strip()
    if not haystack:
        return []

    try:
        haystack_vector = embed_text(haystack)
    except Exception as exc:  # noqa: BLE001 — keep pipeline moving on Ollama blips
        logger.warning(
            "Semantic guideline embed skipped for section=%r: %s",
            str(record.get("section") or "")[:80],
            exc,
        )
        return []

    matches: list[str] = []
    for topic, prototypes in GUIDELINE_TOPIC_PROTOTYPES.items():
        score = max_similarity_vector_to_prototypes(haystack_vector, prototypes)
        if score >= config.SECTION_SIMILARITY_THRESHOLD:
            matches.append(topic)
    return matches


def filter_important_sections(records: list[dict]) -> list[dict]:
    try:
        warmup_prototype_vectors(DRUG_SECTION_PROTOTYPES, GUIDELINE_TOPIC_PROTOTYPES)
    except Exception as exc:  # noqa: BLE001 — keyword filter still works without prototypes
        logger.warning("Prototype embedding warmup failed; semantic section match may be limited: %s", exc)

    total = len(records)
    important: list[dict] = []
    semantic_embed_calls = 0
    progress_every = max(100, total // 20) if total else 100

    logger.info("Filtering %s sections (keyword first, semantic embed only when needed)...", total)

    for index, record in enumerate(records, start=1):
        keyword_matches: list[str] = []
        semantic_matches: list[str] = []

        if is_extracted_table_section(record):
            keyword_matches = guideline_matches(record) or ["tables"]
            output = mark_record(record, sorted(set(keyword_matches)))
            metadata = output.setdefault("metadata", {})
            metadata["section_match_method"] = "extracted_table"
            important.append(output)
            continue

        if record.get("source_type") == "drug_label":
            keyword_matches = drug_matches(record)
            if not keyword_matches:
                semantic_embed_calls += 1
                semantic_matches = _semantic_drug_matches(record)
        elif record.get("source_type") == "guideline":
            keyword_matches = guideline_matches(record)
            if not keyword_matches:
                semantic_embed_calls += 1
                semantic_matches = _semantic_guideline_matches(record)

        merged = sorted(set(keyword_matches) | set(semantic_matches))
        if merged:
            output = mark_record(record, merged)
            metadata = output.setdefault("metadata", {})
            metadata["section_match_method"] = (
                "keyword+semantic" if keyword_matches and semantic_matches else "semantic" if semantic_matches else "keyword"
            )
            important.append(output)

        if index == 1 or index % progress_every == 0 or index == total:
            logger.info(
                "Section filter progress: %s/%s processed, %s important so far, %s semantic embed calls",
                index,
                total,
                len(important),
                semantic_embed_calls,
            )

    logger.info(
        "Section filter complete: %s/%s sections kept (%s semantic embed calls)",
        len(important),
        total,
        semantic_embed_calls,
    )
    return important
