"""Validate that recommendation / safety items are supported by evidence text."""

from __future__ import annotations

import re
from dataclasses import dataclass

from app.core.metrics import increment
from app.modules.citation_validation.hydrate import hydrate_chunks_for_target
from app.modules.citation_validation.links import source_link_for_chunk
from app.modules.citation_validation.terms import (
    SAFETY_TERMS,
    _BASELINE_CLASS_TERMS as DRUG_CLASS_TERMS,
    class_terms,
    safety_terms,
    warning_terms,
)
from app.modules.evidence_quality import quality_score_for_chunk
from app.schemas.graphrag import (
    CitationSupport,
    CitationValidation,
    EvidenceChunk,
    GraphRAGContextResponse,
)
from app.schemas.patient import PatientProfile
from app.schemas.recommendation import MedicationRecommendation, RecommendationResponse


@dataclass(frozen=True)
class EvidenceMatch:
    chunk: EvidenceChunk
    matched_terms: list[str]
    score: float


# source_link_for_chunk imported from links (shared with evidence_linking)


def _tokens(value: str) -> list[str]:
    return [token for token in re.split(r"[^a-z0-9+]+", value.lower()) if len(token) >= 3]


def _contains(text: str, term: str) -> bool:
    term = term.lower()
    if " " in term:
        return term in text
    return bool(re.search(rf"(?<![a-z0-9]){re.escape(term)}(?![a-z0-9])", text))


def _chunk_text(chunk: EvidenceChunk) -> str:
    metadata = chunk.metadata or {}
    values = [
        chunk.document_id,
        chunk.source_type,
        chunk.section or "",
        chunk.text,
        str(metadata.get("title") or ""),
        str(metadata.get("citation") or ""),
        str(metadata.get("source_section") or ""),
        " ".join(str(value) for value in metadata.get("matched_important_topics", []) or []),
    ]
    return " ".join(values).lower()


def _quality_bonus(chunk: EvidenceChunk, preferred_source_types: set[str] | None = None) -> float:
    preferred = preferred_source_types or set()
    source = (chunk.source_type or "").lower()
    if preferred and source in preferred:
        return 4.0
    if source == "guideline":
        return 3.0
    if source == "drug_label":
        return 2.0
    return 0.0


def _reference_terms(refs: list[str]) -> list[str]:
    terms: list[str] = []
    for ref in refs:
        cleaned = (
            ref.replace("guideline_consensus:", " ")
            .replace("fda_label:", " ")
            .replace("week7_", " ")
            .replace("safety_warning:", " ")
        )
        terms.extend(_tokens(cleaned.replace("_", " ")))
    return terms


def _match_chunks(
    chunks: list[EvidenceChunk],
    required_terms: list[str],
    evidence_refs: list[str] | None = None,
    top_k: int = 3,
    *,
    patient: PatientProfile | None = None,
    preferred_source_types: set[str] | None = None,
) -> list[EvidenceMatch]:
    matches: list[EvidenceMatch] = []
    evidence_refs = evidence_refs or []
    ref_terms = _reference_terms(evidence_refs)
    preferred = preferred_source_types or set()
    for chunk in chunks:
        text = _chunk_text(chunk)
        matched = [term for term in required_terms if _contains(text, term)]
        ref_matched = [term for term in ref_terms if _contains(text, term)]
        # Direct chunk-id hit counts as strong ref match
        if chunk.chunk_id in evidence_refs:
            ref_matched = list(set(ref_matched + ["chunk_id_match"]))
        if not matched and not ref_matched:
            continue
        quality = quality_score_for_chunk(chunk, matched + ref_matched, patient=patient)
        score = (
            len(set(matched))
            + (len(set(ref_matched)) * 0.75)
            + _quality_bonus(chunk, preferred)
            + quality
        )
        matches.append(EvidenceMatch(chunk=chunk, matched_terms=matched, score=score))
    return sorted(matches, key=lambda item: (item.score, item.chunk.score), reverse=True)[:top_k]


def _support_status(
    matches: list[EvidenceMatch],
    required_terms: list[str],
    *,
    patient: PatientProfile | None = None,
    preferred_source_types: set[str] | None = None,
) -> tuple[str, str, str, float]:
    if not matches:
        return "missing", "missing_citation", "No evidence passage matched the words we looked for.", 0.0
    all_matched = {term for match in matches for term in match.matched_terms}
    coverage = len(all_matched) / max(len(set(required_terms)), 1)
    best_quality = max(
        quality_score_for_chunk(match.chunk, match.matched_terms, patient=patient) for match in matches
    )
    preferred = preferred_source_types or {"guideline", "drug_label"}
    has_preferred = any((match.chunk.source_type or "").lower() in preferred for match in matches)
    has_authoritative = any(
        (match.chunk.source_type or "").lower() in {"guideline", "drug_label"} for match in matches
    )
    confidence = round(min((coverage * 0.65) + (best_quality * 0.35), 1.0), 3)
    if coverage >= 0.5 and (has_preferred or has_authoritative) and best_quality >= 0.55:
        return "strong", "supported", "Retrieved evidence directly supports this item.", confidence
    if coverage >= 0.25 or best_quality >= 0.6:
        return "weak", "weakly_supported", "Retrieved evidence is relevant but incomplete.", confidence
    return "weak", "unsupported", "Retrieved evidence has low word coverage for this item.", confidence


def _plain_explanation(required: list[str], matched: list[str], status: str) -> str:
    need = ", ".join(required[:10]) or "(none)"
    found = ", ".join(matched[:10]) or "(none)"
    missing = ", ".join([t for t in required if t not in set(matched)][:10]) or "(none)"
    if status == "strong":
        return f"Words looked for: {need}. Words found in passages: {found}."
    if status == "missing":
        return f"Words looked for: {need}. No matching passage found. Still missing: {missing}."
    return f"Words looked for: {need}. Words found: {found}. Still missing: {missing}."


def _citation_support(
    target_id: str,
    target_type: str,
    message_basis: str,
    required_terms: list[str],
    chunks: list[EvidenceChunk],
    evidence_refs: list[str] | None = None,
    *,
    patient: PatientProfile | None = None,
    preferred_source_types: set[str] | None = None,
) -> CitationSupport:
    unique_terms = sorted({term.lower() for term in required_terms if term})
    pool = hydrate_chunks_for_target(
        chunks,
        evidence_refs=evidence_refs,
        required_terms=unique_terms,
        preferred_source_types=preferred_source_types,
    )
    matches = _match_chunks(
        pool,
        unique_terms,
        evidence_refs=evidence_refs,
        patient=patient,
        preferred_source_types=preferred_source_types,
    )
    status, verdict, message, confidence = _support_status(
        matches,
        unique_terms,
        patient=patient,
        preferred_source_types=preferred_source_types,
    )
    best_quality = max(
        (quality_score_for_chunk(match.chunk, match.matched_terms, patient=patient) for match in matches),
        default=0.0,
    )
    matched_terms = sorted({term for match in matches for term in match.matched_terms if term != "chunk_id_match"})
    unmatched = sorted(set(unique_terms) - set(matched_terms))
    return CitationSupport(
        target_id=target_id,
        target_type=target_type,
        evidence_status=status,
        message=f"{message} Basis: {message_basis}",
        required_terms=unique_terms,
        matched_terms=matched_terms,
        unmatched_terms=unmatched,
        evidence_refs=[match.chunk.chunk_id for match in matches],
        source_links=[link for match in matches if (link := source_link_for_chunk(match.chunk))],
        evidence_verdict=verdict,
        confidence=confidence,
        quality_score=round(best_quality, 3),
        explanation=_plain_explanation(unique_terms, matched_terms, status),
    )


def _rollup_status(items: list[CitationSupport]) -> str:
    if not items:
        return "strong"
    if any(item.evidence_status == "missing" for item in items):
        return "missing"
    if any(item.evidence_status == "weak" for item in items):
        return "weak"
    return "strong"


def validate_citations(
    response: RecommendationResponse,
    context: GraphRAGContextResponse,
    *,
    patient: PatientProfile | None = None,
) -> CitationValidation:
    supports: list[CitationSupport] = []
    chunks = list(context.evidence_chunks)

    for item in response.recommendations:
        terms = class_terms(item.drug_class) + safety_terms(" ".join(item.warnings + [item.rationale]))
        refs = item.evidence + item.constraint_ids + item.safety_warning_ids
        supports.append(
            _citation_support(
                target_id=item.drug_class,
                target_type="recommendation",
                message_basis=item.rationale,
                required_terms=terms,
                chunks=chunks,
                evidence_refs=refs,
                patient=patient,
                preferred_source_types={"guideline", "drug_label"},
            )
        )

    for constraint in response.constraints:
        terms = class_terms(constraint.target_drug_class) + safety_terms(constraint.reason)
        supports.append(
            _citation_support(
                target_id=constraint.constraint_id,
                target_type="constraint",
                message_basis=constraint.reason,
                required_terms=terms,
                chunks=chunks,
                evidence_refs=[constraint.evidence_ref or constraint.constraint_id],
                patient=patient,
                preferred_source_types={"guideline", "drug_label"},
            )
        )

    for warning in response.dose_warnings + response.interaction_warnings:
        terms = warning_terms(warning.target, warning.message)
        category = (warning.category or "").lower()
        preferred = {"drug_label"}
        if "dose" not in category and "interaction" not in category:
            preferred = {"guideline", "drug_label"}
        supports.append(
            _citation_support(
                target_id=warning.warning_id,
                target_type=warning.category,
                message_basis=warning.message,
                required_terms=terms,
                chunks=chunks,
                evidence_refs=[getattr(warning, "evidence_ref", None) or warning.warning_id],
                patient=patient,
                preferred_source_types=preferred,
            )
        )

    recommendations = [s for s in supports if s.target_type == "recommendation"]
    safety = [s for s in supports if s.target_type != "recommendation"]
    recommendation_status = _rollup_status(recommendations)
    safety_status = _rollup_status(safety)
    # Overall follows primary recommendations; safety gaps only soften to weak
    if recommendation_status == "missing":
        status = "missing"
    elif recommendation_status == "weak":
        status = "weak"
    elif safety_status in {"missing", "weak"}:
        status = "weak"
    else:
        status = "strong"

    increment("hf_cdss_citation_validation_total", {"status": status})
    for support in supports:
        increment(
            "hf_cdss_citation_support_total",
            {"target_type": support.target_type, "verdict": support.evidence_verdict or support.evidence_status},
        )
    return CitationValidation(
        status=status,
        recommendation_status=recommendation_status,
        safety_status=safety_status,
        supports=supports,
    )


_MISSING_CITE_WARNING = (
    "Citation check could not match a supporting passage for this recommendation; "
    "review the source evidence before acting."
)


def apply_citation_guardrails(
    response: RecommendationResponse,
    citation_validation: CitationValidation | None,
) -> RecommendationResponse:
    """Lower certainty when a primary recommendation lacks citation support."""
    if not citation_validation:
        return response

    by_class = {
        s.target_id: s
        for s in citation_validation.supports
        if s.target_type == "recommendation"
    }
    updated: list[MedicationRecommendation] = []
    for item in response.recommendations:
        support = by_class.get(item.drug_class)
        if not support or support.evidence_status == "strong":
            updated.append(item)
            continue
        warnings = list(item.warnings)
        if _MISSING_CITE_WARNING not in warnings:
            warnings.append(_MISSING_CITE_WARNING)
        if support.explanation:
            detail = f"Citation detail: {support.explanation}"
            if detail not in warnings:
                warnings.append(detail)
        new_status = item.status
        if support.evidence_status == "missing" and item.status.lower() in {
            "consider",
            "initiate",
            "continue",
            "optimize",
        }:
            new_status = "review"
        updated.append(item.model_copy(update={"status": new_status, "warnings": warnings}))
    return response.model_copy(update={"recommendations": updated})
