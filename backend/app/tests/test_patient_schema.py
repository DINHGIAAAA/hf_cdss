import pytest
from app.schemas.patient import PatientProfile


def _valid_patient() -> dict:
    """Base valid patient profile with all normal values."""
    return {
        "patient_identity": {"case_id": "TEST_001"},
        "demographics": {"age": 65, "sex": "male"},
        "vitals": {
            "systolic_bp": {"value": 120},
            "diastolic_bp": {"value": 80},
            "heart_rate": {"value": 72},
            "spo2": {"value": 97},
            "respiratory_rate": {"value": 16},
            "weight_kg": {"value": 75},
            "height_cm": {"value": 170},
        },
        "heart_failure_profile": {"lvef": {"value": 35}},
        "labs": {
            "egfr": {"value": 60},
            "creatinine": {"value": 1.1},
            "potassium": {"value": 4.5},
            "sodium": {"value": 140},
            "hemoglobin": {"value": 13.5},
        },
        "conditions": [{"name": "Heart Failure"}],
        "medications": [{"name": "lisinopril", "status": "active"}],
    }


def _build_patient(**overrides) -> PatientProfile:
    """Build patient with optional field overrides."""
    import copy
    data = copy.deepcopy(_valid_patient())
    for path, value in overrides.items():
        parts = path.split(".")
        if len(parts) == 2:
            section, field = parts
            if section in data and isinstance(data[section], dict):
                data[section][field] = value
            elif section in data and hasattr(data[section], field):
                setattr(data[section], field, value)
        elif len(parts) == 3:
            section, sub, field = parts
            if section in data and isinstance(data[section], dict):
                data[section].setdefault(sub, {})
                data[section][sub][field] = value
    return PatientProfile(**data)


# =============================================================================
# Physiological Range Validation - Valid Values
# =============================================================================

def test_valid_physiological_ranges_all_normal() -> None:
    """All vitals and labs within normal range should pass."""
    patient = PatientProfile(**_valid_patient())
    assert patient.systolic_bp == 120
    assert patient.egfr == 60
    assert patient.vitals.spo2.value == 97


def test_valid_physiological_ranges_boundary_low() -> None:
    """Boundary low values should be accepted."""
    data = _valid_patient()
    data["vitals"]["systolic_bp"] = {"value": 40}
    data["vitals"]["diastolic_bp"] = {"value": 20}
    data["vitals"]["heart_rate"] = {"value": 20}
    data["vitals"]["spo2"] = {"value": 50}
    data["vitals"]["respiratory_rate"] = {"value": 4}
    data["vitals"]["weight_kg"] = {"value": 1.0}
    data["vitals"]["height_cm"] = {"value": 20}
    data["heart_failure_profile"]["lvef"] = {"value": 0}
    data["labs"]["egfr"] = {"value": 0}
    data["labs"]["creatinine"] = {"value": 0.1}
    data["labs"]["potassium"] = {"value": 1.0}
    data["labs"]["sodium"] = {"value": 100.0}
    data["labs"]["hemoglobin"] = {"value": 1.0}
    patient = PatientProfile(**data)
    assert patient.lvef == 0
    assert patient.egfr == 0


def test_valid_physiological_ranges_boundary_high() -> None:
    """Boundary high values should be accepted."""
    data = _valid_patient()
    data["vitals"]["systolic_bp"] = {"value": 300}
    data["vitals"]["diastolic_bp"] = {"value": 200}
    data["vitals"]["heart_rate"] = {"value": 300}
    data["vitals"]["spo2"] = {"value": 100}
    data["vitals"]["respiratory_rate"] = {"value": 60}
    data["vitals"]["weight_kg"] = {"value": 500}
    data["vitals"]["height_cm"] = {"value": 300}
    data["heart_failure_profile"]["lvef"] = {"value": 100}
    data["labs"]["egfr"] = {"value": 200}
    data["labs"]["creatinine"] = {"value": 30.0}
    data["labs"]["potassium"] = {"value": 10.0}
    data["labs"]["sodium"] = {"value": 180.0}
    data["labs"]["hemoglobin"] = {"value": 25.0}
    patient = PatientProfile(**data)
    assert patient.systolic_bp == 300
    assert patient.egfr == 200


def test_valid_physiological_ranges_null_values() -> None:
    """Null values should be allowed (no validation error)."""
    data = _valid_patient()
    data["vitals"]["systolic_bp"] = None
    data["labs"]["egfr"] = None
    data["labs"]["sodium"] = None
    patient = PatientProfile(**data)
    assert patient.systolic_bp is None
    assert patient.egfr is None


def test_valid_physiological_ranges_string_values() -> None:
    """String values in ClinicalValue should bypass numeric validation."""
    data = _valid_patient()
    data["vitals"]["spo2"] = {"value": "not_tested"}
    data["labs"]["sodium"] = {"value": "unknown"}
    # Should not raise - string values bypass range check
    patient = PatientProfile(**data)
    assert patient is not None


# =============================================================================
# Physiological Range Validation - Invalid Values (NEW fields)
# =============================================================================

def test_invalid_spo2_too_high() -> None:
    """SpO2 > 100% should be rejected."""
    with pytest.raises(ValueError, match="Physiological range violations"):
        _build_patient(**{"vitals.spo2": {"value": 105}})


def test_invalid_spo2_too_low() -> None:
    """SpO2 < 50% should be rejected."""
    with pytest.raises(ValueError, match="Physiological range violations"):
        _build_patient(**{"vitals.spo2": {"value": 40}})


def test_invalid_spo2_extreme() -> None:
    """SpO2 = 500 (extreme) should be rejected."""
    with pytest.raises(ValueError, match="spo2=500"):
        _build_patient(**{"vitals.spo2": {"value": 500}})


def test_invalid_systolic_bp_extreme_high() -> None:
    """Systolic BP > 300 should be rejected."""
    with pytest.raises(ValueError, match="Physiological range violations"):
        _build_patient(**{"vitals.systolic_bp": {"value": 900}})


def test_invalid_systolic_bp_negative() -> None:
    """Negative systolic BP should be rejected."""
    with pytest.raises(ValueError, match="systolic_bp=-50"):
        _build_patient(**{"vitals.systolic_bp": {"value": -50}})


def test_invalid_weight_too_high() -> None:
    """Weight > 500 kg should be rejected."""
    with pytest.raises(ValueError, match="Physiological range violations"):
        _build_patient(**{"vitals.weight_kg": {"value": 600}})


def test_invalid_weight_negative() -> None:
    """Negative weight should be rejected."""
    with pytest.raises(ValueError, match="weight_kg=-50"):
        _build_patient(**{"vitals.weight_kg": {"value": -50}})


def test_invalid_height_too_high() -> None:
    """Height > 300 cm should be rejected."""
    with pytest.raises(ValueError, match="Physiological range violations"):
        _build_patient(**{"vitals.height_cm": {"value": 350}})


def test_invalid_height_negative() -> None:
    """Negative height should be rejected."""
    with pytest.raises(ValueError, match="height_cm=-100"):
        _build_patient(**{"vitals.height_cm": {"value": -100}})


def test_invalid_respiratory_rate_too_high() -> None:
    """Respiratory rate > 60 should be rejected."""
    with pytest.raises(ValueError, match="Physiological range violations"):
        _build_patient(**{"vitals.respiratory_rate": {"value": 100}})


def test_invalid_respiratory_rate_too_low() -> None:
    """Respiratory rate < 4 should be rejected."""
    with pytest.raises(ValueError, match="Physiological range violations"):
        _build_patient(**{"vitals.respiratory_rate": {"value": 2}})


def test_invalid_egfr_negative() -> None:
    """Negative eGFR should be rejected."""
    with pytest.raises(ValueError, match="Physiological range violations"):
        _build_patient(**{"labs.egfr": {"value": -10}})


def test_invalid_egfr_zero() -> None:
    """eGFR = 0 should be accepted (dialysis patients)."""
    # eGFR = 0 is valid boundary (dialysis patients)
    patient = _build_patient(**{"labs.egfr": {"value": 0}})
    assert patient.egfr == 0


def test_invalid_egfr_too_high() -> None:
    """eGFR > 200 should be rejected."""
    with pytest.raises(ValueError, match="Physiological range violations"):
        _build_patient(**{"labs.egfr": {"value": 250}})


def test_invalid_sodium_too_low() -> None:
    """Sodium < 100 should be rejected."""
    with pytest.raises(ValueError, match="sodium=50"):
        _build_patient(**{"labs.sodium": {"value": 50}})


def test_invalid_sodium_too_high() -> None:
    """Sodium > 180 should be rejected."""
    with pytest.raises(ValueError, match="Physiological range violations"):
        _build_patient(**{"labs.sodium": {"value": 200}})


def test_invalid_hemoglobin_too_high() -> None:
    """Hemoglobin > 25 should be rejected."""
    with pytest.raises(ValueError, match="Physiological range violations"):
        _build_patient(**{"labs.hemoglobin": {"value": 30}})


def test_invalid_hemoglobin_critically_low() -> None:
    """Hemoglobin < 1.0 should be rejected."""
    with pytest.raises(ValueError, match="Physiological range violations"):
        _build_patient(**{"labs.hemoglobin": {"value": 0.5}})


def test_invalid_potassium_critical_low() -> None:
    """Potassium < 1.0 should be rejected."""
    with pytest.raises(ValueError, match="Physiological range violations"):
        _build_patient(**{"labs.potassium": {"value": 0.5}})


def test_invalid_potassium_critical_high() -> None:
    """Potassium > 10.0 should be rejected."""
    with pytest.raises(ValueError, match="Physiological range violations"):
        _build_patient(**{"labs.potassium": {"value": 12}})


def test_invalid_lvef_negative() -> None:
    """Negative LVEF should be rejected."""
    with pytest.raises(ValueError, match="Physiological range violations"):
        _build_patient(**{"heart_failure_profile.lvef": {"value": -10}})


def test_invalid_lvef_over_100() -> None:
    """LVEF > 100% should be rejected."""
    with pytest.raises(ValueError, match="Physiological range violations"):
        _build_patient(**{"heart_failure_profile.lvef": {"value": 110}})


def test_invalid_multiple_violations() -> None:
    """Multiple violations should all be reported."""
    data = _valid_patient()
    data["vitals"]["spo2"] = {"value": 500}
    data["labs"]["sodium"] = {"value": 50}
    data["vitals"]["systolic_bp"] = {"value": -50}
    with pytest.raises(ValueError) as exc_info:
        PatientProfile(**data)
    error_msg = str(exc_info.value)
    assert "spo2=500" in error_msg
    assert "sodium=50" in error_msg
    assert "systolic_bp=-50" in error_msg


# =============================================================================
# Integration: Test Abnormal Values Rejected
# =============================================================================

def test_clinical_scenario_spO2_500_rejected() -> None:
    """Clinical scenario: SpO2 entered as 500 (typo) should be rejected."""
    data = _valid_patient()
    data["vitals"]["spo2"] = {"value": 500}  # Typo: user meant 95
    with pytest.raises(ValueError, match="spo2=500"):
        PatientProfile(**data)


def test_clinical_scenario_negative_weight_rejected() -> None:
    """Clinical scenario: Negative weight should be rejected."""
    data = _valid_patient()
    data["vitals"]["weight_kg"] = {"value": -50}  # Invalid
    with pytest.raises(ValueError, match="weight_kg=-50"):
        PatientProfile(**data)


def test_clinical_scenario_age_200_rejected() -> None:
    """Clinical scenario: Age > 130 should be rejected (schema level)."""
    data = _valid_patient()
    data["demographics"]["age"] = 200
    with pytest.raises(ValueError, match="less than or equal to 130"):
        PatientProfile(**data)


# =============================================================================
# Legacy Payload Tests (existing)
# =============================================================================

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
