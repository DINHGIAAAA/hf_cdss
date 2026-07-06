from __future__ import annotations

import re
from datetime import date

from app.modules.clinical_entity_boosting import clinical_entity_boost
from app.schemas.graphrag import EvidenceChunk
from app.schemas.patient import PatientProfile


SOURCE_AUTHORITY = {
    "guideline": 0.35,
    "drug_label": 0.3,
    "label": 0.25,
    "trial": 0.25,
    "review": 0.15,
}

HIGH_VALUE_SECTIONS = (
    "recommendation",
    "contraindication",
    "warning",
    "precaution",
    "dosage",
    "renal",
    "potassium",
    "monitoring",
    "drug interaction",
)


def _year(value: object) -> int | None:
    if value is None:
        return None
    text = str(value)
    match = re.search(r"(20\d{2}|19\d{2})", text)
    return int(match.group(1)) if match else None


def _metadata_year(chunk: EvidenceChunk) -> int | None:
    metadata = chunk.metadata or {}
    for key in ("publication_year", "published_year", "revision_year", "effective_year", "year"):
        year = _year(metadata.get(key))
        if year:
            return year
    for key in ("published_at", "publication_date", "revision_date", "effective_date", "downloaded_at"):
        year = _year(metadata.get(key))
        if year:
            return year
    return None


def evidence_level_for_chunk(chunk: EvidenceChunk) -> str:
    source_type = chunk.source_type.lower()
    section = (chunk.section or "").lower()
    if source_type == "guideline":
        return "guideline"
    if source_type == "drug_label":
        if any(term in section for term in ("contraindication", "warning", "precaution")):
            return "drug_label_safety"
        return "drug_label"
    return "source_text"


def quality_score_for_chunk(
    chunk: EvidenceChunk,
    matched_terms: list[str] | None = None,
    *,
    patient: PatientProfile | None = None,
) -> float:
    metadata = chunk.metadata or {}
    matched_terms = matched_terms or []
    score = min(max(float(chunk.score), 0.0), 1.0) * 0.35
    score += SOURCE_AUTHORITY.get(chunk.source_type.lower(), 0.1)

    section_text = " ".join(
        [
            chunk.section or "",
            str(metadata.get("source_section") or ""),
            str(metadata.get("citation") or ""),
        ]
    ).lower()
    if any(term in section_text for term in HIGH_VALUE_SECTIONS):
        score += 0.12
    if chunk.source_url or metadata.get("source_url"):
        score += 0.08
    if chunk.page or metadata.get("page") or metadata.get("page_start"):
        score += 0.05
    if metadata.get("provenance"):
        score += 0.05
    score += clinical_entity_boost(matched_terms, patient=patient, chunk=chunk)

    year = _metadata_year(chunk)
    if year:
        age = max(date.today().year - year, 0)
        score += max(0.0, 0.08 - min(age, 12) * 0.005)

    return round(min(score, 1.0), 3)


def enrich_evidence_chunk(
    chunk: EvidenceChunk,
    matched_terms: list[str] | None = None,
    *,
    patient: PatientProfile | None = None,
) -> EvidenceChunk:
    quality_score = quality_score_for_chunk(chunk, matched_terms, patient=patient)
    return chunk.model_copy(
        update={
            "quality_score": quality_score,
            "evidence_level": evidence_level_for_chunk(chunk),
            "metadata": {
                **(chunk.metadata or {}),
                "quality_score": quality_score,
                "evidence_level": evidence_level_for_chunk(chunk),
            },
        }
    )
