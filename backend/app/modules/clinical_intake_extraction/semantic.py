"""Semantic embedding helpers for clinical intake (catalog match + conversation memory)."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Any

from app.core.config import settings
from app.modules.semantic_retrieval.service import cosine_similarity, embed_documents, embed_query, embedding_index_version
from app.schemas.patient import (
    Condition,
    MedicationStatement,
    PatientIdentity,
    PatientProfile,
    RedFlag,
    SourceTrace,
)


logger = logging.getLogger(__name__)

STRONG_SEMANTIC_MATCH = 0.72


@dataclass(frozen=True)
class CatalogEntry:
    kind: str
    canonical_name: str
    label: str
    drug_class: str | None = None
    aliases: tuple[str, ...] = ()


@dataclass(frozen=True)
class CatalogMatch:
    entry: CatalogEntry
    score: float


_catalog_cache: tuple[str, list[CatalogEntry], list[list[float]]] | None = None


def _normalize_text(text: str) -> str:
    from app.modules.clinical_intake_extraction.service import normalize_text

    return normalize_text(text)


def _is_negated(normalized_text: str, start: int) -> bool:
    from app.modules.clinical_intake_extraction.service import NEGATION_PREFIXES

    context = normalized_text[max(0, start - 24) : start]
    return any(re.search(rf"\b{re.escape(prefix)}\b(?:\s+\w+)?\s*$", context) for prefix in NEGATION_PREFIXES)


def _source_semantic(field: str, label: str, score: float) -> SourceTrace:
    return SourceTrace(
        source_type="semantic_clinical_intake",
        document_id=field,
        source_text=label[:240],
        confidence=min(0.95, 0.55 + score * 0.4),
    )


def _build_catalog_entries() -> list[CatalogEntry]:
    from app.modules.clinical_intake_extraction.service import CONDITIONS, MEDICATIONS, RED_FLAGS

    entries: list[CatalogEntry] = []
    for canonical_name, (drug_class, aliases) in MEDICATIONS.items():
        label = f"{canonical_name}; {'; '.join(aliases)}"
        entries.append(
            CatalogEntry(
                kind="medication",
                canonical_name=canonical_name,
                label=label,
                drug_class=drug_class,
                aliases=aliases,
            )
        )
    for canonical_name, aliases in CONDITIONS.items():
        label = f"{canonical_name}; {'; '.join(aliases)}"
        entries.append(
            CatalogEntry(
                kind="condition",
                canonical_name=canonical_name,
                label=label,
                aliases=aliases,
            )
        )
    for canonical_name, aliases in RED_FLAGS.items():
        label = f"{canonical_name}; {'; '.join(aliases)}"
        entries.append(
            CatalogEntry(
                kind="red_flag",
                canonical_name=canonical_name,
                label=label,
                aliases=aliases,
            )
        )
    return entries


def _catalog_vectors() -> tuple[list[CatalogEntry], list[list[float]]]:
    global _catalog_cache
    version = embedding_index_version()
    if _catalog_cache and _catalog_cache[0] == version:
        return _catalog_cache[1], _catalog_cache[2]
    entries = _build_catalog_entries()
    try:
        vectors = embed_documents([entry.label for entry in entries])
    except Exception as exc:
        logger.warning("Clinical intake catalog embedding failed: %s", exc)
        vectors = []
    _catalog_cache = (version, entries, vectors)
    return entries, vectors


def _alias_match_allowed(normalized_text: str, aliases: tuple[str, ...]) -> bool:
    for alias in sorted(aliases, key=len, reverse=True):
        pattern = rf"(?<![a-z0-9]){re.escape(alias)}(?![a-z0-9])"
        for match in re.finditer(pattern, normalized_text):
            if not _is_negated(normalized_text, match.start()):
                return True
    return False


def _alias_mentioned_only_negated(normalized_text: str, aliases: tuple[str, ...]) -> bool:
    found = False
    for alias in sorted(aliases, key=len, reverse=True):
        pattern = rf"(?<![a-z0-9]){re.escape(alias)}(?![a-z0-9])"
        for match in re.finditer(pattern, normalized_text):
            found = True
            if not _is_negated(normalized_text, match.start()):
                return False
    return found


def semantic_catalog_matches(text: str, *, threshold: float | None = None) -> list[CatalogMatch]:
    if not settings.clinical_intake_semantic_enabled:
        return []

    match_threshold = threshold if threshold is not None else settings.clinical_intake_semantic_threshold
    normalized = _normalize_text(text)
    entries, vectors = _catalog_vectors()
    if not vectors:
        return []

    try:
        query_vector = embed_query(text)
    except Exception as exc:
        logger.warning("Clinical intake query embedding failed: %s", exc)
        return []

    matches: list[CatalogMatch] = []
    seen: set[tuple[str, str]] = set()
    for entry, vector in zip(entries, vectors):
        score = cosine_similarity(query_vector, vector)
        if score < match_threshold:
            continue
        literal_ok = _alias_match_allowed(normalized, entry.aliases) if entry.aliases else False
        if literal_ok:
            pass
        elif score >= STRONG_SEMANTIC_MATCH:
            if entry.aliases and _alias_mentioned_only_negated(normalized, entry.aliases):
                continue
        else:
            continue
        key = (entry.kind, entry.canonical_name.lower())
        if key in seen:
            continue
        seen.add(key)
        matches.append(CatalogMatch(entry=entry, score=score))
    matches.sort(key=lambda item: item.score, reverse=True)
    return matches


def aggregate_conversation_context(
    current_message: str,
    prior_user_messages: list[str],
    *,
    max_messages: int | None = None,
    relevance_threshold: float | None = None,
) -> str:
    if not settings.clinical_intake_history_enabled:
        return current_message.strip()

    limit = max_messages if max_messages is not None else settings.clinical_intake_history_max_messages
    threshold = (
        relevance_threshold
        if relevance_threshold is not None
        else settings.clinical_intake_history_relevance_threshold
    )
    prior = [message.strip() for message in prior_user_messages if message.strip()]
    current = current_message.strip()
    if not prior:
        return current
    prior = prior[-limit:]

    if not settings.clinical_intake_semantic_enabled:
        lines = [f"[Previous] {message}" for message in prior]
        lines.append(f"[Current] {current}")
        return "\n".join(lines)

    try:
        current_vector = embed_query(current)
        selected: list[tuple[float, str]] = []
        for index, message in enumerate(prior):
            keep_recent = index == len(prior) - 1
            score = cosine_similarity(current_vector, embed_query(message))
            if keep_recent or score >= threshold:
                selected.append((score, message))
        if not selected:
            selected = [(0.0, message) for message in prior[-2:]]
        selected.sort(key=lambda item: item[0], reverse=True)
        lines = [f"[Previous relevance={score:.2f}] {message}" for score, message in selected]
        lines.append(f"[Current] {current}")
        return "\n".join(lines)
    except Exception as exc:
        logger.warning("Conversation context aggregation failed; using linear history: %s", exc)
        lines = [f"[Previous] {message}" for message in prior]
        lines.append(f"[Current] {current}")
        return "\n".join(lines)


def semantic_extract_patient(text: str, conversation_id: str) -> PatientProfile | None:
    matches = semantic_catalog_matches(text)
    if not matches:
        return None

    medications: list[MedicationStatement] = []
    conditions: list[Condition] = []
    red_flags: list[RedFlag] = []
    for match in matches:
        entry = match.entry
        source = _source_semantic(entry.kind, entry.label, match.score)
        if entry.kind == "medication":
            medications.append(
                MedicationStatement(
                    name=entry.canonical_name,
                    drug_class=entry.drug_class,
                    status="active",
                    source=source,
                )
            )
        elif entry.kind == "condition":
            conditions.append(Condition(name=entry.canonical_name, status="active", source=source))
        elif entry.kind == "red_flag":
            red_flags.append(RedFlag(name=entry.canonical_name, status="present", source=source))

    return PatientProfile(
        patient_identity=PatientIdentity(case_id=conversation_id),
        conditions=conditions,
        medications=medications,
        red_flags=red_flags,
    )


def clear_catalog_cache() -> None:
    global _catalog_cache
    _catalog_cache = None
