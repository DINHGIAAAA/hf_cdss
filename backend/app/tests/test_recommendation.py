from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def _post_recommend(patient: dict) -> dict:
    response = client.post("/recommend", json={"patient": patient})

    assert response.status_code == 200
    return response.json()


def test_recommendation_returns_week3_constraint_aware_contract() -> None:
    payload = _post_recommend(
        {
            "case_id": "CASE_TEST",
            "lvef": 30,
            "egfr": 28,
            "potassium": 5.4,
            "systolic_bp": 92,
            "heart_rate": 58,
            "comorbidities": ["CKD"],
            "current_medications": [],
            "allergies": [],
        }
    )

    assert payload["case_id"] == "CASE_TEST"
    assert payload["patient_summary"]["hf_type"] == "HFrEF"
    assert payload["patient_summary"]["renal_status"] == "severely_reduced"
    assert payload["overall_status"] == "blocked"

    risk_names = {risk["name"] for risk in payload["risk_flags"]}
    assert {"renal_impairment", "hyperkalemia", "hypotension", "bradycardia"} <= risk_names

    constraints = payload["constraints"]
    assert any(item["target_drug_class"] == "MRA" and item["action"] == "avoid" for item in constraints)
    assert any(item["target_drug_class"] == "ARNI/ACEi/ARB" for item in constraints)
    assert any(item["target_drug_class"] == "beta_blocker" for item in constraints)

    recommendations = {item["drug_class"]: item for item in payload["recommendations"]}
    assert recommendations["Mineralocorticoid receptor antagonist"]["status"] == "avoid"
    assert recommendations["SGLT2 inhibitor"]["status"] == "consider_with_caution"
    assert recommendations["SGLT2 inhibitor"]["constraint_ids"]
    assert "clinical decision support" in payload["disclaimer"]


def test_recommendation_clean_hfref_case_has_consider_statuses() -> None:
    payload = _post_recommend(
        {
            "case_id": "CASE_CLEAN",
            "lvef": 32,
            "egfr": 78,
            "potassium": 4.4,
            "systolic_bp": 118,
            "heart_rate": 74,
            "comorbidities": ["Hypertension"],
            "current_medications": ["amlodipine"],
            "allergies": [],
        }
    )

    assert payload["overall_status"] == "approved"
    assert payload["risk_flags"] == []
    assert payload["constraints"] == []
    assert {item["status"] for item in payload["recommendations"]} == {"consider"}


def test_recommendation_non_hfref_case_requires_review() -> None:
    payload = _post_recommend(
        {
            "case_id": "CASE_HFPEF",
            "lvef": 55,
            "egfr": 70,
            "potassium": 4.2,
            "systolic_bp": 120,
            "heart_rate": 80,
            "comorbidities": [],
            "current_medications": [],
            "allergies": [],
        }
    )

    assert payload["overall_status"] == "approved"
    assert payload["patient_summary"]["hf_type"] == "HFpEF"
    assert {item["status"] for item in payload["recommendations"]} == {"review"}


def test_recommendation_missing_safety_data_uses_caution() -> None:
    payload = _post_recommend(
        {
            "case_id": "CASE_MISSING_SAFETY",
            "lvef": 30,
            "systolic_bp": 96,
            "comorbidities": ["CKD", "Hypertension"],
            "current_medications": ["furosemide", "metoprolol", "aspirin"],
            "allergies": [],
        }
    )

    risk_names = {risk["name"] for risk in payload["risk_flags"]}
    assert {"missing_egfr", "missing_potassium", "missing_heart_rate"} <= risk_names
    assert payload["overall_status"] == "approved_with_warnings"

    recommendations = {item["drug_class"]: item for item in payload["recommendations"]}
    assert recommendations["Mineralocorticoid receptor antagonist"]["status"] == "consider_with_caution"
    assert recommendations["SGLT2 inhibitor"]["status"] == "consider_with_caution"
    assert recommendations["Evidence-based beta blocker"]["status"] == "consider_with_caution"
