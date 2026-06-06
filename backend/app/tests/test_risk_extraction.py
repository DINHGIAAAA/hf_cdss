from app.modules.clinical_normalization.service import normalize_patient
from app.modules.risk_extraction.service import extract_risks
from app.schemas.patient import PatientProfile


def _risk_names(patient: PatientProfile) -> set[str]:
    return {risk.name for risk in extract_risks(normalize_patient(patient))}


def test_extracts_core_risks() -> None:
    names = _risk_names(
        PatientProfile(
            case_id="RISK_001",
            lvef=30,
            egfr=28,
            potassium=5.6,
            systolic_bp=88,
            heart_rate=55,
            comorbidities=["Diabetes"],
            current_medications=["a", "b", "c", "d", "e"],
            allergies=[],
        )
    )

    assert names == {
        "renal_impairment",
        "hyperkalemia",
        "hypotension",
        "bradycardia",
        "polypharmacy",
        "diabetes",
    }


def test_missing_lvef_flag() -> None:
    assert "missing_lvef" in _risk_names(PatientProfile(case_id="RISK_002"))


def test_missing_egfr_and_potassium_do_not_create_false_risks() -> None:
    names = _risk_names(PatientProfile(case_id="RISK_003", lvef=35))

    assert "renal_impairment" not in names
    assert "hyperkalemia" not in names
    assert {"missing_egfr", "missing_potassium", "missing_sbp", "missing_heart_rate"} <= names


def test_ckd_history_when_egfr_not_reduced() -> None:
    names = _risk_names(
        PatientProfile(case_id="RISK_004", lvef=35, egfr=70, comorbidities=["CKD"])
    )

    assert "ckd_history" in names
    assert "renal_impairment" not in names
