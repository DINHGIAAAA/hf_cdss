from app.core.config import settings
from app.modules.evidence_filter import (
    filter_evidence_chunks,
    passes_negative_evidence_filter,
    patient_profile_entities,
)
from app.modules.evidence_quality import enrich_evidence_chunk
from app.schemas.graphrag import EvidenceChunk
from app.schemas.patient import PatientProfile


def _chunk(
    chunk_id: str,
    *,
    text: str,
    score: float = 0.7,
    section: str = "RENAL",
    document_id: str = "spironolactone_label",
    metadata: dict | None = None,
) -> EvidenceChunk:
    return EvidenceChunk(
        chunk_id=chunk_id,
        document_id=document_id,
        source_type="drug_label",
        section=section,
        text=text,
        score=score,
        metadata=metadata or {},
    )


def test_patient_profile_entities_include_medications_and_abnormal_labs() -> None:
    patient = PatientProfile(
        case_id="CASE_1",
        current_medications=["spironolactone"],
        comorbidities=["CKD"],
        egfr=24,
        potassium=5.6,
    )

    entities = patient_profile_entities(patient)

    assert "spironolactone" in entities
    assert "egfr" in entities
    assert "hyperkalemia" in entities
    assert "heart" not in entities or "heart rate" in entities


def test_negative_filter_drops_low_quality_and_irrelevant_chunks() -> None:
    patient = PatientProfile(case_id="CASE_2", egfr=24, current_medications=["spironolactone"])
    relevant = enrich_evidence_chunk(
        _chunk(
            "renal",
            text="Avoid MRA when eGFR is less than 30 mL/min/1.73m2 and monitor potassium.",
            score=0.82,
        ),
        ["egfr", "mra", "potassium"],
        patient=patient,
    )
    noisy = enrich_evidence_chunk(
        _chunk(
            "noise",
            text="Administrative contact information for the publisher.",
            section="CONTACT",
            score=0.2,
            document_id="publisher_info",
        ),
        [],
        patient=patient,
    )
    generic = enrich_evidence_chunk(
        _chunk(
            "generic",
            text="General wellness advice unrelated to kidney function or medications.",
            section="OVERVIEW",
            score=0.55,
            document_id="wellness_doc",
        ),
        ["wellness"],
        patient=patient,
    )

    filtered = filter_evidence_chunks(
        [relevant, generic, noisy],
        patient=patient,
        terms=["egfr", "mra", "spironolactone"],
        top_k=1,
    )

    assert [chunk.chunk_id for chunk in filtered] == ["renal"]


def test_negative_filter_keeps_constraint_pinned_chunks() -> None:
    patient = PatientProfile(case_id="CASE_3", egfr=24)
    pinned = enrich_evidence_chunk(
        _chunk(
            "pinned",
            text="Pinned constraint evidence.",
            score=0.1,
            metadata={"constraint_pinned": True},
        ),
        [],
        patient=patient,
    )

    assert passes_negative_evidence_filter(pinned, patient=patient, patient_entities=["egfr"]) is True


def test_negative_filter_backfills_when_too_few_results(monkeypatch) -> None:
    monkeypatch.setattr(settings, "evidence_negative_filter_min_results", 2)
    patient = PatientProfile(case_id="CASE_4", egfr=24, current_medications=["spironolactone"])

    relevant = enrich_evidence_chunk(
        _chunk("renal", text="eGFR below 30 requires caution with MRA therapy.", score=0.8),
        ["egfr", "mra"],
        patient=patient,
    )
    fallback = enrich_evidence_chunk(
        _chunk("fallback", text="Publisher overview without patient-specific terms.", score=0.6),
        [],
        patient=patient,
    )

    filtered = filter_evidence_chunks(
        [relevant, fallback],
        patient=patient,
        terms=["egfr", "mra"],
        top_k=2,
    )

    assert len(filtered) == 2
    assert filtered[0].chunk_id == "renal"
