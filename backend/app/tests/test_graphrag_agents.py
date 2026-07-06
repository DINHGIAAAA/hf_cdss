from app.tests.conftest import api_path


HFREF_CASE = {
    "case_id": "GRAPHRAG_CASE",
    "lvef": 28,
    "egfr": 32,
    "potassium": 5.2,
    "systolic_bp": 94,
    "heart_rate": 56,
    "comorbidities": ["CKD", "Atrial fibrillation"],
    "current_medications": ["metoprolol", "furosemide", "apixaban"],
    "allergies": [],
}


def test_graphrag_context_returns_graph_and_evidence(client) -> None:
    response = client.post(api_path("/graphrag/context"), json={"patient": HFREF_CASE, "top_k": 4})

    assert response.status_code == 200
    payload = response.json()
    assert payload["case_id"] == "GRAPHRAG_CASE"
    assert "egfr" in payload["query_terms"]
    assert payload["graph_facts"]
    assert payload["evidence_chunks"]
    assert "Retrieved" in payload["context_summary"]
    assert "local_relationships" in payload["retrieval_sources"]
    assert "local_chunks" in payload["retrieval_sources"]


def test_verify_runs_agent_verdicts(client) -> None:
    response = client.post(api_path("/verify"), json={"patient": HFREF_CASE})

    assert response.status_code == 200
    payload = response.json()
    assert payload["case_id"] == "GRAPHRAG_CASE"
    agent_names = {item["agent_name"] for item in payload["agent_results"]}
    assert {
        "safety_agent",
        "missing_data_agent",
        "evidence_agent",
        "guideline_alignment_agent",
        "citation_validator_agent",
        "final_reviewer_agent",
    } <= agent_names
    assert payload["final_verdict"] in {"pass", "warning", "fail"}
    assert payload["context"]["evidence_chunks"]
    assert payload["citation_validation"]["status"] in {"strong", "weak", "missing"}
