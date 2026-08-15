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
            "care_context": {"clinician_question": "Should I increase MRA dose?"},
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
    check = check_missing_fields(patient, clinical_intent="dose_adjustment")
    assert any(item.field == "creatinine" for item in check.missing_fields)


def test_arni_question_requires_acei_washout_when_on_acei() -> None:
    from app.modules.missing_fields.service import build_missing_fields_prompt

    patient = PatientProfile.model_validate(
        {
            **_demo_like_patient().model_dump(mode="python"),
            "medications": [
                {"name": "spironolactone", "status": "active"},
                {"name": "lisinopril", "status": "active", "drug_class": "ACEi"},
            ],
        }
    )
    check = check_missing_fields(
        patient,
        clinical_state={"focus_medication_classes": ["ARNI/ACEi/ARB"], "mentioned_medications": [{"name": "ARNI"}]},
    )
    assert any(item.field == "acei_last_dose_hours_ago" for item in check.missing_fields)
    en_prompt = build_missing_fields_prompt(check)
    assert "ACEi last dose timing" in en_prompt
    assert "ARNI" in en_prompt


def test_missing_fields_prompt_includes_multi_question_context() -> None:
    from app.modules.missing_fields.service import MissingField, MissingFieldCheck, build_missing_fields_prompt

    check = MissingFieldCheck(
        status="missing_required_fields",
        missing_fields=[MissingField(field="egfr", label="eGFR", reason="needed")],
        present_fields=[],
    )
    prompt = build_missing_fields_prompt(
        check,
        active_question="What about ARNI?",
        question_index=1,
        total_questions=2,
    )
    assert "question 1/2" in prompt
    assert "What about ARNI?" in prompt


def test_merge_patient_persists_acei_last_dose_hours() -> None:
    from app.modules.chat.service import _apply_extracted_updates, _merge_patient
    from app.modules.clinical_intake_extraction.service import _regex_extract_patient_from_message

    base = _demo_like_patient()
    assert base.care_context.acei_last_dose_hours_ago is None

    extracted = _regex_extract_patient_from_message("Last ACEi dose was 48 hours ago", base.case_id)
    assert extracted.care_context.acei_last_dose_hours_ago == 48.0

    reordered = _regex_extract_patient_from_message("ACEi last dose 40 hours ago", base.case_id)
    assert reordered.care_context.acei_last_dose_hours_ago == 40.0

    merged = _merge_patient(base, extracted)
    assert merged.care_context.acei_last_dose_hours_ago == 48.0

    fast_path = _apply_extracted_updates(base, extracted)
    assert fast_path.care_context.acei_last_dose_hours_ago == 48.0

    check = check_missing_fields(
        merged,
        clinical_state={"focus_medication_classes": ["ARNI/ACEi/ARB"], "mentioned_medications": [{"name": "ARNI"}]},
    )
    assert not any(item.field == "acei_last_dose_hours_ago" for item in check.missing_fields)
