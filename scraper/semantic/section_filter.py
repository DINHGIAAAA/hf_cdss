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
    text = (record.get("text") or "")[:4000]
    haystack = f"{section}\n{text}".strip()
    if not haystack:
        return []

    try:
        haystack_vector = embed_text(haystack)
    except Exception as exc:
        logger.warning("Drug section haystack embedding failed: %s", exc)
        return []

    matches: list[str] = []
    for canonical, prototypes in DRUG_SECTION_PROTOTYPES.items():
        aliases = DRUG_SECTION_ALIASES.get(canonical, {canonical})
        if section in aliases:
            matches.append(canonical)
            continue
        try:
            score = max_similarity_vector_to_prototypes(haystack_vector, prototypes)
        except Exception as exc:
            logger.warning("Drug section embedding failed for %s: %s", canonical, exc)
            continue
        if score >= config.SECTION_SIMILARITY_THRESHOLD:
            matches.append(canonical)
    return matches


def _semantic_guideline_matches(record: dict) -> list[str]:
    haystack = f"{record.get('section', '')}\n{record.get('text', '')}"[:4000].strip()
    if not haystack:
        return []

    try:
        haystack_vector = embed_text(haystack)
    except Exception as exc:
        logger.warning("Guideline haystack embedding failed: %s", exc)
        return []

    matches: list[str] = []
    for topic, prototypes in GUIDELINE_TOPIC_PROTOTYPES.items():
        try:
            score = max_similarity_vector_to_prototypes(haystack_vector, prototypes)
        except Exception as exc:
            logger.warning("Guideline topic embedding failed for %s: %s", topic, exc)
            continue
        if score >= config.SECTION_SIMILARITY_THRESHOLD:
            matches.append(topic)
    return matches


def filter_important_sections(records: list[dict]) -> list[dict]:
    warmup_prototype_vectors(DRUG_SECTION_PROTOTYPES, GUIDELINE_TOPIC_PROTOTYPES)

    important: list[dict] = []
    for record in records:
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
            semantic_matches = _semantic_drug_matches(record)
        elif record.get("source_type") == "guideline":
            keyword_matches = guideline_matches(record)
            semantic_matches = _semantic_guideline_matches(record)

        merged = sorted(set(keyword_matches) | set(semantic_matches))
        if merged:
            output = mark_record(record, merged)
            metadata = output.setdefault("metadata", {})
            metadata["section_match_method"] = (
                "keyword+semantic" if keyword_matches and semantic_matches else "semantic" if semantic_matches else "keyword"
            )
            important.append(output)
    return important
