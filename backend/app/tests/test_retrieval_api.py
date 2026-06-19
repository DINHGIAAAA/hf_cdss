from app.tests.conftest import api_path


def test_retrieval_search_returns_graph_and_evidence(client) -> None:
    response = client.get(
        api_path("/evidence/search"),
        params={"q": "dapagliflozin renal heart failure", "top_k": 4},
    )

    assert response.status_code == 200
    payload = response.json()
    assert "dapagliflozin" in payload["query_terms"]
    assert payload["graph_facts"]
    assert payload["evidence_chunks"]


def test_retrieval_search_legacy_alias_still_works(client) -> None:
    response = client.get(
        api_path("/retrieval/search"),
        params={"q": "dapagliflozin renal heart failure", "top_k": 4},
    )

    assert response.status_code == 200
    payload = response.json()
    assert "dapagliflozin" in payload["query_terms"]


def test_retrieval_context_returns_summary(client) -> None:
    response = client.post(
        api_path("/retrieval/context"),
        json={"query": "mra hyperkalemia egfr", "top_k": 4},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["query"] == "mra hyperkalemia egfr"
    assert payload["graph_facts"]
    assert payload["evidence_chunks"]
    assert "Retrieved" in payload["context_summary"]
