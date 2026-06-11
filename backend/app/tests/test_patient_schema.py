from app.schemas.patient import PatientProfile


def test_patient_profile_accepts_legacy_flat_payload() -> None:
    patient = PatientProfile(
        case_id="LEGACY_001",
        lvef=30,
        egfr=28,
        potassium=5.6,
        systolic_bp=88,
        heart_rate=55,
        comorbidities=["CKD"],
        current_medications=["spironolactone"],
        allergies=["penicillin"],
    )

    assert patient.case_id == "LEGACY_001"
    assert patient.lvef == 30
    assert patient.egfr == 28
    assert patient.potassium == 5.6
    assert patient.systolic_bp == 88
    assert patient.heart_rate == 55
    assert patient.comorbidities == ["CKD"]
    assert patient.current_medications == ["spironolactone"]
    assert patient.allergies == ["penicillin"]


def test_patient_profile_accepts_nested_domain_payload() -> None:
    patient = PatientProfile(
        patient_identity={"case_id": "NESTED_001", "full_name": "Nguyen Van A"},
        demographics={"age": 68, "sex": "male"},
        heart_failure_profile={"lvef": {"value": 32, "unit": "%"}, "nyha_class": "III"},
        labs={"egfr": {"value": 35}, "potassium": {"value": 4.9}},
        vitals={"systolic_bp": {"value": 105}, "heart_rate": {"value": 72}},
        conditions=[{"name": "Diabetes"}],
        medications=[{"name": "dapagliflozin", "drug_class": "SGLT2i"}],
        allergy_statements=[],
    )

    assert patient.case_id == "NESTED_001"
    assert patient.patient_identity.full_name == "Nguyen Van A"
    assert patient.lvef == 32
    assert patient.egfr == 35
    assert patient.comorbidities == ["Diabetes"]
    assert patient.current_medications == ["dapagliflozin"]
