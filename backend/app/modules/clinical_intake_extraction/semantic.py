"""Semantic embedding helpers for clinical intake (catalog match + conversation memory)."""

from __future__ import annotations

import logging
import re
import threading
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
_catalog_cache_lock = threading.Lock()


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
    with _catalog_cache_lock:
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
        if literal_ok or score >= STRONG_SEMANTIC_MATCH:
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
    last_assistant_message: str | None = None,
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

    def _with_previous_answer(body: str) -> str:
        prior_answer = (last_assistant_message or "").strip()
        if not prior_answer:
            return body
        excerpt = prior_answer if len(prior_answer) <= 4000 else prior_answer[:3997] + "..."
        header = "[Your previous answer]"
        if body.strip():
            return f"{header}\n{excerpt}\n\n{body}"
        return f"{header}\n{excerpt}"

    if not prior:
        body = f"[Current] {current}" if current else ""
        return _with_previous_answer(body)
    prior = prior[-limit:]

    if not settings.clinical_intake_semantic_enabled:
        lines = [f"[Previous] {message}" for message in prior]
        lines.append(f"[Current] {current}")
        return _with_previous_answer("\n".join(lines))

    try:
        texts = [current, *prior]
        vectors = embed_documents(texts)
        if len(vectors) != len(texts):
            raise RuntimeError("embedding batch size mismatch")
        current_vector = vectors[0]
        selected: list[tuple[float, str]] = []
        for index, message in enumerate(prior):
            keep_recent = index == len(prior) - 1
            score = cosine_similarity(current_vector, vectors[index + 1])
            if keep_recent or score >= threshold:
                selected.append((score, message))
        if not selected:
            selected = [(0.0, message) for message in prior[-2:]]
        selected.sort(key=lambda item: item[0], reverse=True)
        lines = [f"[Previous relevance={score:.2f}] {message}" for score, message in selected]
        lines.append(f"[Current] {current}")
        return _with_previous_answer("\n".join(lines))
    except Exception as exc:
        logger.warning("Conversation context aggregation failed; using linear history: %s", exc)
        lines = [f"[Previous] {message}" for message in prior]
        lines.append(f"[Current] {current}")
        return _with_previous_answer("\n".join(lines))


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
    with _catalog_cache_lock:
        _catalog_cache = None


def _split_by_conjunction(raw: str) -> list[str]:
    """Split a sentence with multiple question fragments using English question-word boundaries."""
    import re

    # English question-word patterns that mark a new independent question.
    QWORD_PATTERNS = [
        r"and\s+(?:should\s+)?(?:I\s+)?(?:we\s+)?(?:consider|add|start|try)\b",
        r"and\s+(?:what\s+about|how\s+about)\b",
        r"also\b",
        r"what\s+about\b",
        r"how\s+about\b",
        r"what\s+(?:about\s+)?(?:is\s+)?(?:the\s+)?(?:effect\s+)?(?:on|of)\b",
        r"what\s+(?:else|next)\b",
        r"is\s+it\s+(?:necessary|needed|recommended)\b",
        r"do\s+I\s+(?:also|need)\b",
        r"should\s+I\s+(?:also|also\s+consider|add)\b",
        r"then\s+(?:what|how|about)\b",
        r"what\s+if\b",
        # "does it"/"is there"/"can we"/etc. only mark a NEW question when they
        # continue a prior clause via a conjunction — bare, they're just how the
        # message's one real question naturally opens (e.g. after a clinical
        # presentation paragraph), and splitting there fabricates a false first
        # "question" out of that non-question preamble.
        r"and\s+does\s+it\b",
        r"and\s+is\s+there\b",
        r"and\s+can\s+(?:we|I)\b",
        r"and\s+could\s+(?:we|I)\b",
        r"and\s+would\s+(?:it|you)\b",
        r",\s*also\b",
    ]

    pattern = "|".join(f"(?:{p})" for p in QWORD_PATTERNS)
    parts: list[str] = []
    last = 0
    for m in re.finditer(pattern, raw, re.IGNORECASE):
        start = m.start()
        if start > last:
            chunk = raw[last:start].strip()
            chunk = re.sub(r"[,]+\s*$", "", chunk).strip()
            if chunk:
                parts.append(chunk)
        last = m.start()
    if last < len(raw):
        tail = raw[last:].strip()
        tail = re.sub(r"^[,]+\s*", "", tail).strip()
        if tail:
            parts.append(tail)
    return parts


def detect_multi_question(message: str) -> list[str]:
    """Split a multi-question message into individual questions (English only).

    Two detection strategies, tried in order:

    1. Explicit '?' delimiters  — "MRA or SGLT2i? What about ARNI?"
    2. Question-word boundaries inside a clause — "Should I add MRA and also consider SGLT2i"

    Returns [message] if only one question is found so the normal flow is unchanged.
    """
    from app.modules.clinical_intake_extraction.service import normalize_text

    raw = (message or "").strip()
    if not raw:
        return [raw]

    # Strategy 1: split on '?' (explicit delimiters)
    parts = [s.strip() for s in raw.split("?") if s.strip()]
    MIN_QUESTION_LEN = 5  # Allow short abbreviations like "SGLT2i?" (7 chars after strip)
    questions = [s for s in parts if len(normalize_text(s)) >= MIN_QUESTION_LEN]
    if len(questions) > 1:
        return [f"{q}?" for q in questions]

    # Strategy 2: detect English question-word boundaries inside the single clause
    by_qword = _split_by_conjunction(raw)
    qword_questions = [s for s in by_qword if len(normalize_text(s)) >= MIN_QUESTION_LEN]
    if len(qword_questions) > 1:
        return [f"{q}?" for q in qword_questions]

    # No multi-question detected
    return [raw]
