"""Hybrid keyword + embedding + borderline LLM section relevance filtering."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field

from scraper.prompts.section_importance import SECTION_IMPORTANCE_SYSTEM_PROMPT
from scraper.semantic import config
from scraper.semantic.embeddings import embed_text, max_similarity_vector_to_prototypes, warmup_prototype_vectors
from scraper.semantic.llm_client import call_llm_json, llm_available
from scraper.semantic.topic_prototypes import DRUG_SECTION_PROTOTYPES, GUIDELINE_TOPIC_PROTOTYPES
from scraper.transform.extract_important_sections import (
    DRUG_SECTION_ALIASES,
    drug_matches,
    guideline_matches,
    mark_record,
    normalize,
)
from scraper.transform.table_sections import is_extracted_table_section

logger = logging.getLogger(__name__)

# High-signal body cues for low-embed rescue (stricter than broad guideline topic terms).
_LOW_SCORE_RESCUE_CUES: list[tuple[str, tuple[str, ...]]] = [
    (
        "dosing",
        (
            "starting dose",
            "target dose",
            "maintenance dose",
            "dose titration",
            "titrate",
            "mg twice daily",
            "mg once daily",
            "mg/day",
            " mcg ",
        ),
    ),
    (
        "contraindications",
        (
            "contraindicated",
            "do not use",
            "must not be used",
            "absolute contraindication",
        ),
    ),
    (
        "warnings",
        (
            "boxed warning",
            "black box",
            "serious risk",
            "life-threatening",
        ),
    ),
    (
        "drug interactions",
        (
            "drug-drug interaction",
            "concomitant use with",
            "co-administration",
            "coadministration",
            "avoid concomitant",
        ),
    ),
    (
        "monitoring",
        (
            "monitor potassium",
            "monitor renal",
            "laboratory monitoring",
            "check egfr",
            "recheck creatinine",
        ),
    ),
    (
        "hyperkalemia",
        ("hyperkalemia", "hyperkalaemia", "serum potassium >"),
    ),
    (
        "renal dysfunction",
        ("egfr <", "crcl <", "severe renal impairment", "dialysis"),
    ),
]


@dataclass
class SemanticProbe:
    matches: list[str] = field(default_factory=list)
    best_score: float = 0.0
    best_topic: str | None = None
    topic_scores: dict[str, float] = field(default_factory=dict)


@dataclass
class _PendingBorderline:
    record: dict
    probe: SemanticProbe


def _probe_from_prototypes(
    haystack_vector: list[float],
    prototypes: dict[str, list[str]],
    *,
    keep_threshold: float,
) -> SemanticProbe:
    topic_scores: dict[str, float] = {}
    matches: list[str] = []
    best_score = 0.0
    best_topic: str | None = None
    for topic, proto_list in prototypes.items():
        score = max_similarity_vector_to_prototypes(haystack_vector, proto_list)
        topic_scores[topic] = score
        if score > best_score:
            best_score = score
            best_topic = topic
        if score >= keep_threshold:
            matches.append(topic)
    return SemanticProbe(
        matches=matches,
        best_score=best_score,
        best_topic=best_topic,
        topic_scores=topic_scores,
    )


def _semantic_drug_probe(record: dict) -> SemanticProbe:
    section = normalize(record.get("section", ""))
    text = (record.get("text") or "")[:2000]
    haystack = f"{section}\n{text}".strip()
    if not haystack:
        return SemanticProbe()

    for canonical, aliases in DRUG_SECTION_ALIASES.items():
        if section in aliases:
            return SemanticProbe(matches=[canonical], best_score=1.0, best_topic=canonical)

    try:
        haystack_vector = embed_text(haystack)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Semantic drug embed skipped for section=%r: %s", section[:80], exc)
        return SemanticProbe()

    return _probe_from_prototypes(
        haystack_vector,
        DRUG_SECTION_PROTOTYPES,
        keep_threshold=config.SECTION_SIMILARITY_THRESHOLD,
    )


def _semantic_guideline_probe(record: dict) -> SemanticProbe:
    haystack = f"{record.get('section', '')}\n{record.get('text', '')}"[:2000].strip()
    if not haystack:
        return SemanticProbe()

    try:
        haystack_vector = embed_text(haystack)
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "Semantic guideline embed skipped for section=%r: %s",
            str(record.get("section") or "")[:80],
            exc,
        )
        return SemanticProbe()

    return _probe_from_prototypes(
        haystack_vector,
        GUIDELINE_TOPIC_PROTOTYPES,
        keep_threshold=config.SECTION_SIMILARITY_THRESHOLD,
    )


def is_borderline_score(score: float) -> bool:
    low = config.SECTION_BORDERLINE_LOW_THRESHOLD
    keep = config.SECTION_SIMILARITY_THRESHOLD
    if low >= keep:
        return False
    return low <= score < keep


def low_score_text_rescue_matches(record: dict) -> list[str]:
    """Keep low-embed sections when body text has unambiguous clinical safety/dose cues."""
    if not config.SECTION_LOW_SCORE_TEXT_RESCUE_ENABLED:
        return []
    haystack = f"{record.get('section', '')}\n{record.get('text', '')}".lower()
    if not haystack.strip():
        return []
    hits: list[str] = []
    for topic, cues in _LOW_SCORE_RESCUE_CUES:
        if any(cue in haystack for cue in cues):
            hits.append(topic)
    return hits


def _allowed_topics(source_type: str) -> list[str]:
    if source_type == "drug_label":
        return sorted(DRUG_SECTION_PROTOTYPES.keys())
    return sorted(GUIDELINE_TOPIC_PROTOTYPES.keys())


def review_borderline_section_with_llm(
    record: dict,
    *,
    probe: SemanticProbe,
) -> list[str]:
    """Ask LLM whether a borderline section should be kept. Returns topic list or []."""
    source_type = str(record.get("source_type") or "")
    allowed = _allowed_topics(source_type)
    if not allowed:
        return []

    title = str(record.get("section") or "")
    text = str(record.get("text") or "")[:1500]
    user_prompt = json.dumps(
        {
            "source_type": source_type,
            "section_title": title,
            "text": text,
            "embed_best_score": round(probe.best_score, 4),
            "embed_best_topic": probe.best_topic,
            "allowed_topics": allowed,
            "keep_threshold": config.SECTION_SIMILARITY_THRESHOLD,
            "borderline_low": config.SECTION_BORDERLINE_LOW_THRESHOLD,
        },
        ensure_ascii=False,
    )
    payload = call_llm_json(
        SECTION_IMPORTANCE_SYSTEM_PROMPT,
        user_prompt,
        max_tokens=config.SECTION_BORDERLINE_LLM_MAX_TOKENS,
    )
    if not isinstance(payload, dict):
        return []

    keep = payload.get("keep")
    if keep is not True and str(keep).lower() not in {"true", "1", "yes"}:
        return []

    topic = str(payload.get("topic") or "").strip()
    if topic in allowed:
        return [topic]
    if probe.best_topic and probe.best_topic in allowed:
        return [probe.best_topic]
    return [allowed[0]]


def _semantic_drug_matches(record: dict) -> list[str]:
    return _semantic_drug_probe(record).matches


def _semantic_guideline_matches(record: dict) -> list[str]:
    return _semantic_guideline_probe(record).matches


def _append_important(
    important: list[dict],
    record: dict,
    topics: list[str],
    *,
    match_method: str,
    probe: SemanticProbe | None = None,
) -> None:
    output = mark_record(record, sorted(set(topics)))
    metadata = output.setdefault("metadata", {})
    metadata["section_match_method"] = match_method
    if probe and probe.best_score:
        metadata["section_embed_best_score"] = round(probe.best_score, 4)
        metadata["section_embed_best_topic"] = probe.best_topic
    important.append(output)


def filter_important_sections(records: list[dict]) -> list[dict]:
    try:
        warmup_prototype_vectors(DRUG_SECTION_PROTOTYPES, GUIDELINE_TOPIC_PROTOTYPES)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Prototype embedding warmup failed; semantic section match may be limited: %s", exc)

    total = len(records)
    important: list[dict] = []
    pending_borderline: list[_PendingBorderline] = []
    semantic_embed_calls = 0
    low_score_rescued = 0
    progress_every = max(100, total // 20) if total else 100

    logger.info(
        "Filtering %s sections (keyword → embed → low-score text rescue → "
        "borderline LLM prioritized in [%.2f, %.2f), cap=%s)...",
        total,
        config.SECTION_BORDERLINE_LOW_THRESHOLD,
        config.SECTION_SIMILARITY_THRESHOLD,
        config.SECTION_BORDERLINE_LLM_MAX,
    )

    # Pass 1: keyword / embed keep, queue borderline, rescue strong body cues below low threshold.
    for index, record in enumerate(records, start=1):
        if is_extracted_table_section(record):
            keyword_matches = guideline_matches(record) or ["tables"]
            _append_important(important, record, keyword_matches, match_method="extracted_table")
            continue

        keyword_matches: list[str] = []
        probe = SemanticProbe()
        if record.get("source_type") == "drug_label":
            keyword_matches = drug_matches(record)
            if not keyword_matches:
                semantic_embed_calls += 1
                probe = _semantic_drug_probe(record)
        elif record.get("source_type") == "guideline":
            keyword_matches = guideline_matches(record)
            if not keyword_matches:
                semantic_embed_calls += 1
                probe = _semantic_guideline_probe(record)

        semantic_matches = list(probe.matches)
        merged = sorted(set(keyword_matches) | set(semantic_matches))
        if merged:
            method = (
                "keyword+semantic"
                if keyword_matches and semantic_matches
                else "semantic"
                if semantic_matches
                else "keyword"
            )
            _append_important(important, record, merged, match_method=method, probe=probe)
        elif is_borderline_score(probe.best_score) and config.SECTION_BORDERLINE_LLM_ENABLED:
            pending_borderline.append(_PendingBorderline(record=record, probe=probe))
        else:
            rescue = low_score_text_rescue_matches(record)
            if rescue and probe.best_score < config.SECTION_BORDERLINE_LOW_THRESHOLD:
                low_score_rescued += 1
                _append_important(
                    important,
                    record,
                    rescue,
                    match_method="low_score_text_rescue",
                    probe=probe,
                )

        if index == 1 or index % progress_every == 0 or index == total:
            logger.info(
                "Section filter pass1: %s/%s processed, %s kept, %s queued borderline, "
                "%s semantic embeds, %s low-score text rescues",
                index,
                total,
                len(important),
                len(pending_borderline),
                semantic_embed_calls,
                low_score_rescued,
            )

    # Pass 2: LLM borderline highest-score first (so cap drops the least relevant first).
    borderline_candidates = len(pending_borderline)
    pending_borderline.sort(key=lambda item: item.probe.best_score, reverse=True)
    review_budget = min(borderline_candidates, config.SECTION_BORDERLINE_LLM_MAX) if config.SECTION_BORDERLINE_LLM_ENABLED else 0
    borderline_capped = borderline_candidates > review_budget
    borderline_llm_calls = 0
    borderline_kept = 0
    llm_ready: bool | None = None

    if review_budget and borderline_candidates:
        if llm_ready is None:
            llm_ready = llm_available()
            if not llm_ready:
                logger.warning("Borderline section LLM unavailable; borderline queue left dropped")

    if llm_ready:
        for item in pending_borderline[:review_budget]:
            borderline_llm_calls += 1
            llm_topics = review_borderline_section_with_llm(item.record, probe=item.probe)
            if llm_topics:
                borderline_kept += 1
                _append_important(
                    important,
                    item.record,
                    llm_topics,
                    match_method="borderline_llm",
                    probe=item.probe,
                )
            if borderline_llm_calls == 1 or borderline_llm_calls % 50 == 0 or borderline_llm_calls == review_budget:
                logger.info(
                    "Section filter borderline LLM: %s/%s reviewed, %s kept",
                    borderline_llm_calls,
                    review_budget,
                    borderline_kept,
                )

    if borderline_capped:
        dropped_by_cap = borderline_candidates - review_budget
        logger.warning(
            "Borderline LLM cap reached (cap=%s, candidates=%s, dropped_without_llm=%s). "
            "Raise HF_CDSS_SECTION_BORDERLINE_LLM_MAX if needed.",
            config.SECTION_BORDERLINE_LLM_MAX,
            borderline_candidates,
            dropped_by_cap,
        )

    logger.info(
        "Section filter complete: %s/%s sections kept "
        "(%s semantic embeds, %s borderline candidates, %s borderline LLM kept, "
        "%s low-score text rescues, capped=%s)",
        len(important),
        total,
        semantic_embed_calls,
        borderline_candidates,
        borderline_kept,
        low_score_rescued,
        borderline_capped,
    )
    return important
