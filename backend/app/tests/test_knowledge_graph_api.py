from app.tests.conftest import api_path


def test_kg_drug_classes_returns_gdmt_classes(client) -> None:
    response = client.get(api_path("/kg/drug-classes"))

    assert response.status_code == 200
    payload = response.json()
    classes = {item["drug_class"] for item in payload["drug_classes"]}
    assert {"ARNI/ACEi/ARB", "beta_blocker", "MRA", "SGLT2i"} <= classes
    assert all("constraint_count" in item for item in payload["drug_classes"])


def test_kg_constraints_resolves_aliases(client) -> None:
    response = client.get(api_path("/kg/constraints/mra"))

    assert response.status_code == 200
    payload = response.json()
    constraint_ids = {item["constraint_id"] for item in payload["constraints"]}
    assert "MRA_HARD_RENAL_OR_K" in constraint_ids


def test_kg_recommendations_for_hfref_returns_core_classes(client) -> None:
    response = client.get(api_path("/kg/recommendations/HFrEF"))

    assert response.status_code == 200
    payload = response.json()
    recommendations = payload["recommendations"]
    assert len(recommendations) == 4
    assert {item["recommendation"] for item in recommendations} == {"guideline_directed"}


def test_kg_interactions_returns_interaction_facts(client) -> None:
    response = client.get(api_path("/kg/interactions"), params={"drug": "dapagliflozin", "top_k": 5})

    assert response.status_code == 200
    payload = response.json()
    assert payload["drug"] == "dapagliflozin"
    assert payload["interactions"]
    assert all("interaction" in item["metadata"].get("claim_type", "") for item in payload["interactions"])


def test_kg_interactions_requires_drug_query(client) -> None:
    response = client.get(api_path("/kg/interactions"))

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"
