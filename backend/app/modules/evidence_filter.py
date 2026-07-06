"""Negative filtering for retrieved evidence chunks."""

from __future__ import annotations

import re

from app.core.config import settings
from app.modules.clinical_entity_boosting import matched_terms_for_chunk
from app.modules.drug_normalization.service import expand_drug_search_terms
from app.modules.evidence_quality import enrich_evidence_chunk, quality_score_for_chunk
from app.schemas.graphrag import EvidenceChunk
from app.schemas.patient import PatientProfile


def _tokenize(value: str) -> list[str]:
    return [token for token in re.split(r"[^a-z0-9+]+", value.lower()) if len(token) >= 3]


def _add_terms(terms: set[str], values: list[str]) -> None:
    for value in values:
        terms.update(_tokenize(value))


def patient_profile_entities(patient: PatientProfile) -> list[str]:
    """Patient-specific entities used for negative filtering (excludes generic HF baselines)."""
    from app.modules.graphrag.service import CLINICAL_TERMS, DRUG_CLASS_TERMS

    terms: set[str] = set()
    _add_terms(terms, patient.current_medications)
    _add_terms(terms, patient.comorbidities)
    _add_terms(terms, patient.allergies)

    for medication in patient.current_medications:
        _add_terms(terms, expand_drug_search_terms(medication))
        medication_lower = medication.lower()
        for class_terms in DRUG_CLASS_TERMS.values():
            if any(term in medication_lower for term in class_terms):
                _add_terms(terms, class_terms)

    for comorbidity in patient.comorbidities:
        lower = comorbidity.lower()
        for label, clinical_terms in CLINICAL_TERMS.items():
            if label in lower:
                _add_terms(terms, clinical_terms)

    if patient.lvef is not None:
        _add_terms(terms, ["lvef", "ejection fraction"])
        if patient.lvef <= 40:
            _add_terms(terms, ["hfref", "reduced ejection fraction"])
        else:
            terms.add("hfpef")
    if patient.egfr is not None:
        _add_terms(terms, ["egfr", "gfr", "renal"])
        if patient.egfr < 60:
            _add_terms(terms, ["ckd", "kidney"])
    if patient.potassium is not None:
        terms.add("potassium")
        if patient.potassium >= 5.0:
            _add_terms(terms, ["hyperkalemia", "k+"])
    if patient.systolic_bp is not None:
        _add_terms(terms, ["systolic", "blood pressure", "hypotension"])
    if patient.heart_rate is not None:
        _add_terms(terms, ["heart rate", "bradycardia"])
    if patient.creatinine is not None:
        terms.add("creatinine")
    if patient.inr is not None:
        terms.add("inr")

    return sorted(terms)


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
