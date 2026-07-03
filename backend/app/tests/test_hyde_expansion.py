import asyncio

import pytest

from app.core.config import settings
from app.modules.graphrag import hyde_expansion
from app.modules.graphrag.hyde_expansion import (
    build_semantic_retrieval_query,
    generate_hyde_document,
    invalidate_hyde_cache,
    should_expand_with_hyde,
)
from app.modules.graphrag.service import build_graphrag_context_async
from app.schemas.graphrag import GraphRAGContextRequest
from app.schemas.patient import PatientProfile


def _patient(**overrides) -> PatientProfile:
    base = {
        "case_id": "CASE_HYDE",
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


@pytest.fixture(autouse=True)
def _reset_hyde_cache() -> None:
    invalidate_hyde_cache()
    yield
    invalidate_hyde_cache()


def test_generate_hyde_document_uses_llm_and_cache(monkeypatch) -> None:
    monkeypatch.setattr(settings, "hyde_retrieval_enabled", True)
    monkeypatch.setattr(settings, "llm_api_type", "chat_completions")
    calls = {"count": 0}

    class FakeResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            return {
                "choices": [
                    {
                        "message": {
                            "content": (
                                "Spironolactone requires careful monitoring of serum potassium and renal function. "
                                "Hyperkalemia risk increases when potassium is above 5.0 mmol/L or eGFR is below 30."
                            )
                        }
                    }
                ]
            }

    class FakeClient:
        async def post(self, *args, **kwargs):
            calls["count"] += 1
            return FakeResponse()

    monkeypatch.setattr(hyde_expansion, "get_async_client", lambda *_args, **_kwargs: FakeClient())

    patient = _patient()
    query = "co nen tiep spiro k+ 5.7"
    first = asyncio.run(generate_hyde_document(query, patient))
    second = asyncio.run(generate_hyde_document(query, patient))

    assert first
    assert "spironolactone" in first.lower()
    assert first == second
    assert calls["count"] == 1


def test_build_semantic_retrieval_query_combines_baseline(monkeypatch) -> None:
    monkeypatch.setattr(settings, "hyde_retrieval_combine_baseline", True)
    combined = build_semantic_retrieval_query(
        baseline_query="co nen tiep spiro",
        hyde_document="Spironolactone requires potassium monitoring in heart failure.",
    )
    assert "Spironolactone requires potassium monitoring" in combined
    assert "co nen tiep spiro" in combined


def test_should_expand_with_hyde_respects_flags(monkeypatch) -> None:
    monkeypatch.setattr(settings, "hyde_retrieval_enabled", False)
    monkeypatch.setattr(settings, "llm_api_type", "chat_completions")
    assert should_expand_with_hyde("co nen tiep spironolactone") is False

    monkeypatch.setattr(settings, "hyde_retrieval_enabled", True)
    assert should_expand_with_hyde("short") is False
    assert should_expand_with_hyde("co nen tiep spironolactone") is True


def test_build_graphrag_context_async_uses_hyde_for_chroma(monkeypatch) -> None:
    monkeypatch.setattr(settings, "hyde_retrieval_enabled", True)
    monkeypatch.setattr(settings, "llm_api_type", "chat_completions")
    monkeypatch.setattr(settings, "retrieval_backend", "databases")
    captured: dict[str, str] = {}

    async def fake_hyde(*_args, **_kwargs):
        return "Mineralocorticoid receptor antagonists require potassium and renal monitoring in HFrEF."

    def fake_chroma(query: str, top_k: int):
        captured["query"] = query
        return []

    monkeypatch.setattr("app.modules.graphrag.service.generate_hyde_document", fake_hyde)
    monkeypatch.setattr("app.modules.graphrag.service.retrieve_chroma", fake_chroma)
    monkeypatch.setattr("app.modules.graphrag.service.retrieve_neo4j", lambda *_args, **_kwargs: [])
    monkeypatch.setattr("app.modules.graphrag.service.retrieve_graph_facts", lambda *_args, **_kwargs: [])
    monkeypatch.setattr("app.modules.graphrag.service.retrieve_evidence_chunks", lambda *_args, **_kwargs: [])

    response = asyncio.run(
        build_graphrag_context_async(
            GraphRAGContextRequest(
                patient=_patient(),
                query="co nen tiep spiro k+ 5.7",
                top_k=4,
            )
        )
    )

    assert response.hyde_used is True
    assert "Mineralocorticoid receptor antagonists" in captured["query"]
    assert "hyde" in response.retrieval_sources or response.hyde_document
