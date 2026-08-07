import pytest

from app.core.config import settings
from app.modules.graphrag.retrieval_profile import retrieval_options_for_profile
from app.schemas.graphrag import GraphRAGContextRequest
from app.tests.conftest import hfref_patient


def test_fast_profile_disables_expensive_retrieval_steps() -> None:
    options = retrieval_options_for_profile("fast")
    assert options.use_hyde is False
    assert options.multi_query is False
    assert options.query_decomposition is False
    assert options.rerank is False
    assert options.expand_chunk_window is False


@pytest.mark.asyncio
async def test_chat_fast_profile_skips_hyde(monkeypatch) -> None:
    from app.modules.graphrag import service as graphrag_service

    hyde_called = False

    async def _fake_hyde(*_args, **_kwargs):
        nonlocal hyde_called
        hyde_called = True
        return "fake hyde document long enough to pass sanitize minimum length requirement here"

    monkeypatch.setattr(graphrag_service, "generate_hyde_document", _fake_hyde)
    monkeypatch.setattr(
        graphrag_service,
        "retrieve_hybrid_evidence_chunks",
        lambda *args, **kwargs: ([], ["bm25"]),
    )
    monkeypatch.setattr(graphrag_service, "retrieve_graph_facts", lambda *_a, **_k: [])
    monkeypatch.setattr(graphrag_service.settings, "retrieval_backend", "local")

    request = GraphRAGContextRequest(
        patient=hfref_patient(),
        query="Co nen tang MRA cho benh nhan HFrEF?",
        top_k=3,
        retrieval_profile="fast",
    )
    response = await graphrag_service.build_graphrag_context_async(request)
    assert hyde_called is False
    assert "retrieval_profile_fast" in response.retrieval_sources
