from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def test_retrieval_search_returns_graph_and_evidence() -> None:
    response = client.get("/retrieval/search", params={"q": "dapagliflozin renal heart failure", "top_k": 4})

    assert response.status_code == 200
    payload = response.json()
    assert "dapagliflozin" in payload["query_terms"]
    assert payload["graph_facts"]
    assert payload["evidence_chunks"]


def test_retrieval_context_returns_summary() -> None:
    response = client.post(
        "/retrieval/context",
        json={"query": "mra hyperkalemia egfr", "top_k": 4},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["query"] == "mra hyperkalemia egfr"
    assert payload["graph_facts"]
    assert payload["evidence_chunks"]
    assert "Retrieved" in payload["context_summary"]

