from app.modules.clinical_normalization.service import (
    classify_bp_status,
    classify_hf_type,
    classify_hr_status,
    classify_potassium_status,
    classify_renal_status,
    detect_polypharmacy,
    normalize_patient,
)
from app.schemas.patient import PatientProfile


def test_classify_hf_type() -> None:
    assert classify_hf_type(40) == "HFrEF"
    assert classify_hf_type(45) == "HFmrEF"
    assert classify_hf_type(55) == "HFpEF"
    assert classify_hf_type(None) == "unknown"


def test_classify_renal_status() -> None:
    assert classify_renal_status(None) == "missing"
    assert classify_renal_status(12) == "kidney_failure"
    assert classify_renal_status(28) == "severely_reduced"
    assert classify_renal_status(38) == "moderately_reduced"
    assert classify_renal_status(55) == "mildly_reduced"
    assert classify_renal_status(90) == "preserved"


def test_classify_potassium_status() -> None:
    assert classify_potassium_status(None) == "missing"
    assert classify_potassium_status(3.2) == "low"
    assert classify_potassium_status(4.9) == "normal"
    assert classify_potassium_status(5.2) == "elevated"
    assert classify_potassium_status(5.5) == "high"


def test_classify_bp_status() -> None:
    assert classify_bp_status(None) == "missing"
    assert classify_bp_status(88) == "hypotension"
    assert classify_bp_status(96) == "low"
    assert classify_bp_status(120) == "acceptable"
    assert classify_bp_status(140) == "elevated"


def test_classify_hr_status() -> None:
    assert classify_hr_status(None) == "missing"
    assert classify_hr_status(55) == "bradycardia"
    assert classify_hr_status(75) == "acceptable"
    assert classify_hr_status(110) == "tachycardia"


def test_detect_polypharmacy() -> None:
    assert detect_polypharmacy(["a", "b", "c", "d", "e"])
    assert not detect_polypharmacy([])


def test_normalize_patient_terms_and_observations() -> None:
    profile = normalize_patient(
        PatientProfile(
            case_id="NORM_001",
            lvef=30,
            egfr=28,
            potassium=5.6,
            systolic_bp=88,
            heart_rate=55,
            comorbidities=[" Chronic_Kidney Disease ", "Diabetes"],
            current_medications=[" Metoprolol Succinate "],
            allergies=[],
        )
    )

    assert profile.hf_type == "HFrEF"
    assert profile.renal_status == "severely_reduced"
    assert profile.potassium_status == "high"
    assert profile.bp_status == "hypotension"
    assert profile.hr_status == "bradycardia"
    assert "chronic kidney disease" in profile.normalized_comorbidities
    assert profile.observations["lvef"] == 30
