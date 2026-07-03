from app.modules.graphrag.service import query_terms_for_patient
from app.schemas.patient import PatientProfile


def _patient(**overrides) -> PatientProfile:
    base = {
        "case_id": "CASE_GRAPHRAG",
        "lvef": 28,
        "egfr": 24,
        "potassium": 5.7,
        "systolic_bp": 98,
        "heart_rate": 54,
        "comorbidities": ["CKD"],
        "current_medications": ["spironolactone"],
        "allergies": [],
    }
    base.update(overrides)
    return PatientProfile(**base)


def test_query_terms_include_conversation_history() -> None:
    patient = _patient(current_medications=[])
    terms = query_terms_for_patient(
        patient,
        "co nen tiep tuc spironolactone khong",
        conversation_history=[
            "Benh nhan eGFR 24 va kali 5.7",
            "Dang dung furosemide va digoxin",
        ],
    )
    assert "egfr" in terms
    assert "spironolactone" in terms or "5" in " ".join(terms)


def test_query_terms_include_clinical_state() -> None:
    patient = _patient()
    clinical_state = {
        "intent": "safety_check",
        "hf_type": "HFrEF",
        "focus_medication_classes": ["MRA"],
        "active_medication_classes": ["MRA"],
        "conditions": ["CKD"],
        "key_values": {"egfr": 24, "potassium": 5.7},
        "safety_state": {"hyperkalemia_risk": True, "renal_risk": True},
        "mentioned_medications": [{"name": "spironolactone", "drug_class": "MRA"}],
    }
    terms = query_terms_for_patient(patient, "review MRA safety", clinical_state=clinical_state)
    assert "mra" in terms
    assert "potassium" in terms or "hyperkalemia" in terms
