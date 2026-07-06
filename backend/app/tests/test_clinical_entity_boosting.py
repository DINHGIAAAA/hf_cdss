from app.modules.clinical_entity_boosting import (
    EntityTier,
    classify_term,
    classify_term_tier,
    clinical_entity_boost,
    threshold_proximity_boost,
)
from app.modules.evidence_quality import quality_score_for_chunk
from app.schemas.graphrag import EvidenceChunk
from app.schemas.patient import PatientProfile


def _chunk(text: str, **metadata) -> EvidenceChunk:
    return EvidenceChunk(
        chunk_id="chunk-1",
        document_id="spironolactone_label",
        source_type="drug_label",
        section="RENAL IMPAIRMENT",
        text=text,
        score=0.6,
        metadata=metadata,
    )


def test_classify_term_tier_groups_fine_grained_entities() -> None:
    assert classify_term_tier("egfr") == EntityTier.LAB_CRITICAL
    assert classify_term_tier("potassium") == EntityTier.LAB_CRITICAL
    assert classify_term_tier("bnp") == EntityTier.LAB_MONITOR
    assert classify_term_tier("mra") == EntityTier.DRUG_CLASS
    assert classify_term_tier("spironolactone") == EntityTier.DRUG_NAME
    assert classify_term_tier("contraindicated") == EntityTier.SAFETY
    assert classify_term_tier("heart failure") == EntityTier.CONDITION


def test_patient_critical_lab_terms_get_higher_multiplier(monkeypatch) -> None:
    monkeypatch.setattr("app.modules.clinical_entity_boosting.settings.clinical_entity_patient_critical_multiplier", 1.65)
    monkeypatch.setattr("app.modules.clinical_entity_boosting.settings.clinical_entity_patient_lab_affinity_multiplier", 1.40)

    patient = PatientProfile(case_id="CASE_1", egfr=24)
    critical_boost = clinical_entity_boost(["egfr"], patient=patient)
    normal_patient_boost = clinical_entity_boost(["egfr"], patient=PatientProfile(case_id="CASE_2", egfr=70))

    assert critical_boost > normal_patient_boost


def test_threshold_proximity_boost_stronger_for_critical_egfr(monkeypatch) -> None:
    monkeypatch.setattr("app.modules.clinical_entity_boosting.settings.clinical_entity_threshold_boost_max", 0.22)
    monkeypatch.setattr("app.modules.clinical_entity_boosting.settings.clinical_entity_threshold_critical_multiplier", 1.35)

    patient = PatientProfile(case_id="CASE_1", egfr=24)
    chunk = _chunk(
        "Mineralocorticoid receptor antagonists should be avoided when estimated glomerular "
        "filtration rate falls below 30 mL/min/1.73m2."
    )

    boost = threshold_proximity_boost(chunk, patient)

    assert boost >= 0.14


def test_quality_score_prefers_threshold_relevant_chunk_for_low_egfr_patient() -> None:
    patient = PatientProfile(case_id="CASE_2", egfr=24, potassium=4.8)
    renal_chunk = _chunk(
        "Avoid MRA when eGFR is less than 30 mL/min/1.73m2 and monitor potassium.",
    )
    generic_chunk = _chunk(
        "General lifestyle advice for patients with heart failure.",
        document_id="lifestyle_doc",
        section="LIFESTYLE",
    )

    renal_score = quality_score_for_chunk(
        renal_chunk,
        ["egfr", "mra", "potassium"],
        patient=patient,
    )
    generic_score = quality_score_for_chunk(
        generic_chunk,
        ["heart", "failure"],
        patient=patient,
    )

    assert renal_score > generic_score + 0.08


def test_clinical_entity_boost_prioritizes_drug_class_over_generic_terms() -> None:
    drug_boost = clinical_entity_boost(["mra", "spironolactone"])
    generic_boost = clinical_entity_boost(["heart", "failure", "patient"])

    assert drug_boost > generic_boost
