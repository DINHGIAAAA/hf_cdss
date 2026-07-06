"""Negative filtering for retrieved evidence chunks."""

from __future__ import annotations

from app.core.config import settings
from app.modules.clinical_entity_boosting import matched_terms_for_chunk
from app.modules.clinical_terms import patient_profile_entities
from app.modules.evidence_quality import enrich_evidence_chunk, quality_score_for_chunk
from app.schemas.graphrag import EvidenceChunk
from app.schemas.patient import PatientProfile


def passes_negative_evidence_filter(
    chunk: EvidenceChunk,
    *,
    patient: PatientProfile | None = None,
    terms: list[str] | None = None,
    patient_entities: list[str] | None = None,
    min_quality: float | None = None,
) -> bool:
    metadata = chunk.metadata or {}
    if metadata.get("constraint_pinned"):
        return True

    matched = matched_terms_for_chunk(chunk, terms or [])
    quality = chunk.quality_score
    if quality is None:
        quality = quality_score_for_chunk(chunk, matched, patient=patient)

    threshold = min_quality if min_quality is not None else settings.evidence_negative_filter_min_quality_score
    if quality < threshold:
        return False

    if settings.evidence_negative_filter_require_patient_entity and patient is not None:
        entities = patient_entities if patient_entities is not None else patient_profile_entities(patient)
        if entities and not matched_terms_for_chunk(chunk, entities):
            return False

    return True


def filter_evidence_chunks(
    chunks: list[EvidenceChunk],
    *,
    patient: PatientProfile | None = None,
    terms: list[str] | None = None,
    top_k: int | None = None,
) -> list[EvidenceChunk]:
    if not chunks or not settings.evidence_negative_filter_enabled:
        return chunks[:top_k] if top_k is not None else chunks

    patient_entities = patient_profile_entities(patient) if patient is not None else []
    passed: list[EvidenceChunk] = []
    rejected: list[EvidenceChunk] = []

    for chunk in chunks:
        matched = matched_terms_for_chunk(chunk, terms or [])
        enriched = enrich_evidence_chunk(chunk, matched, patient=patient)
        if passes_negative_evidence_filter(
            enriched,
            patient=patient,
            terms=terms,
            patient_entities=patient_entities,
        ):
            passed.append(enriched)
        else:
            rejected.append(enriched)

    target = top_k if top_k is not None else len(chunks)
    min_results = min(settings.evidence_negative_filter_min_results, target)
    if len(passed) < min_results and rejected:
        rejected.sort(key=lambda item: item.quality_score or 0.0, reverse=True)
        needed = min_results - len(passed)
        passed.extend(rejected[:needed])

    return passed[:target]
