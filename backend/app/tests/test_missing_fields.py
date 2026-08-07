from app.modules.missing_fields.service import check_missing_fields
from app.schemas.patient import PatientProfile


def _demo_like_patient(*, creatinine: float | None = None) -> PatientProfile:
    labs = {
        "egfr": {"value": 42, "unit": "mL/min/1.73m2"},
        "potassium": {"value": 4.8, "unit": "mmol/L"},
    }
    if creatinine is not None:
        labs["creatinine"] = {"value": creatinine, "unit": "mg/dL"}
    return PatientProfile.model_validate(
        {
            "patient_identity": {"case_id": "demo_tran_minh_hfref"},
            "demographics": {"age": 68, "sex": "male"},
            "heart_failure_profile": {"lvef": {"value": 28}, "nyha_class": "III"},
            "labs": labs,
            "vitals": {
                "systolic_bp": {"value": 108},
                "heart_rate": {"value": 72},
                "weight_kg": {"value": 74},
            },
            "conditions": [{"name": "HFrEF", "status": "active"}],
            "medications": [{"name": "spironolactone", "status": "active"}],
            "allergy_statements": [{"substance": "no known drug allergies", "status": "active"}],
            "red_flags": [{"name": "stable", "status": "absent"}],
            "care_context": {"clinician_question": "Co tang lieu MRA?"},
        }
    )


def test_dose_intent_does_not_require_creatinine_when_egfr_present() -> None:
    patient = _demo_like_patient()
    check = check_missing_fields(patient, clinical_intent="dose_adjustment")
    assert check.status == "complete"
    assert not any(item.field == "creatinine" for item in check.missing_fields)


def test_dose_intent_still_requires_renal_lab_without_egfr_or_creatinine() -> None:
    patient = _demo_like_patient()
    patient.labs.egfr = None
    check = check_missing_fields(patient, clinical_intent="start_medication")
    assert any(item.field == "creatinine" for item in check.missing_fields)
