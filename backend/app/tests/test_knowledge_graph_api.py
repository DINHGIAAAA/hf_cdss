from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def test_kg_drug_classes_returns_gdmt_classes() -> None:
    response = client.get("/kg/drug-classes")

    assert response.status_code == 200
    payload = response.json()
    classes = {item["drug_class"] for item in payload["drug_classes"]}
    assert {"ARNI/ACEi/ARB", "beta_blocker", "MRA", "SGLT2i"} <= classes
    assert all("constraint_count" in item for item in payload["drug_classes"])


def test_kg_constraints_resolves_aliases() -> None:
    response = client.get("/kg/constraints/mra")

    assert response.status_code == 200
    payload = response.json()
    constraint_ids = {item["constraint_id"] for item in payload["constraints"]}
    assert "MRA_HARD_RENAL_OR_K" in constraint_ids


def test_kg_recommendations_for_hfref_returns_core_classes() -> None:
    response = client.get("/kg/recommendations/HFrEF")

    assert response.status_code == 200
    payload = response.json()
    recommendations = payload["recommendations"]
    assert len(recommendations) == 4
    assert {item["recommendation"] for item in recommendations} == {"guideline_directed"}


def test_kg_interactions_returns_interaction_facts() -> None:
    response = client.get("/kg/interactions", params={"drug": "dapagliflozin", "top_k": 5})

    assert response.status_code == 200
    payload = response.json()
    assert payload["drug"] == "dapagliflozin"
    assert payload["interactions"]
    assert all("interaction" in item["metadata"].get("claim_type", "") for item in payload["interactions"])

