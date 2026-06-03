from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


PATIENT = {
    "case_id": "API_001",
    "lvef": 30,
    "egfr": 28,
    "potassium": 5.6,
    "systolic_bp": 88,
    "heart_rate": 55,
    "comorbidities": ["Diabetes"],
    "current_medications": ["a", "b", "c", "d", "e"],
    "allergies": [],
}


def test_normalize_api() -> None:
    response = client.post("/normalize", json={"patient": PATIENT})

    assert response.status_code == 200
    assert response.json()["normalized_profile"]["hf_type"] == "HFrEF"


def test_risks_api() -> None:
    response = client.post("/risks", json={"patient": PATIENT})

    assert response.status_code == 200
    names = {risk["name"] for risk in response.json()["risk_flags"]}
    assert "renal_impairment" in names
    assert "hyperkalemia" in names


def test_constraints_api() -> None:
    response = client.post("/constraints", json={"patient": PATIENT})

    assert response.status_code == 200
    constraints = response.json()["constraints"]
    assert any(item["target_drug_class"] == "MRA" and item["action"] == "avoid" for item in constraints)
    assert any(item["target_drug_class"] == "beta_blocker" for item in constraints)
