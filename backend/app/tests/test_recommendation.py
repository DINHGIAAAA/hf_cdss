from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def test_recommendation_returns_week1_contract() -> None:
    response = client.post(
        "/recommend",
        json={
            "patient": {
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
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["case_id"] == "CASE_TEST"
    assert payload["patient_summary"]["hf_type"] == "HFrEF"
    assert payload["overall_status"] == "approved_with_warnings"
    assert {risk["name"] for risk in payload["risk_flags"]} == {
        "renal_impairment",
        "hyperkalemia",
    }
    assert payload["recommendations"][0]["drug_class"] == "SGLT2 inhibitor"
    assert "clinical decision support" in payload["disclaimer"]
