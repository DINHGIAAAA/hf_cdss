import sys
from types import SimpleNamespace

from app.core.config import settings
from app.modules.semantic_retrieval import service as semantic_service
from app.modules.semantic_retrieval import cohere_rerank
from app.schemas.graphrag import EvidenceChunk


def _chunks() -> list[EvidenceChunk]:
    return [
        EvidenceChunk(
            chunk_id="weak",
            document_id="a",
            source_type="drug_label",
            section="DOSAGE",
            text="Unrelated dose text.",
            score=0.95,
        ),
        EvidenceChunk(
            chunk_id="strong",
            document_id="b",
            source_type="guideline",
            section="RENAL",
            text="Mineralocorticoid receptor antagonists should be avoided when eGFR falls below 30.",
            score=0.1,
        ),
    ]


def test_cohere_rerank_reorders_chunks(monkeypatch) -> None:
    monkeypatch.setattr(settings, "semantic_rerank_enabled", True)
    monkeypatch.setattr(settings, "semantic_rerank_provider", "cohere")
    monkeypatch.setattr(settings, "cohere_api_key", "test-key")
    monkeypatch.setattr(settings, "cohere_rerank_weight", 1.0)

    class FakeClient:
        def rerank(self, **_kwargs):
            return SimpleNamespace(
                results=[
                    SimpleNamespace(index=1, relevance_score=0.92),
                    SimpleNamespace(index=0, relevance_score=0.11),
                ]
            )

    monkeypatch.setitem(sys.modules, "cohere", SimpleNamespace(Client=lambda **_kwargs: FakeClient()))

    reranked = semantic_service.rerank_evidence_chunks(
        "eGFR 24 co dung MRA duoc khong",
        _chunks(),
        top_k=2,
    )

    assert [chunk.chunk_id for chunk in reranked] == ["strong", "weak"]
    assert reranked[0].metadata["rerank_provider"] == "cohere"
    assert reranked[0].metadata["cohere_relevance_score"] == 0.92


def test_cohere_rerank_falls_back_to_bi_encoder(monkeypatch) -> None:
    monkeypatch.setattr(settings, "semantic_rerank_enabled", True)
    monkeypatch.setattr(settings, "semantic_rerank_provider", "cohere")
    monkeypatch.setattr(settings, "cohere_api_key", "test-key")
    monkeypatch.setattr(settings, "semantic_rerank_weight", 1.0)
    def _raise_cohere(*_args, **_kwargs):
        raise RuntimeError("cohere down")

    monkeypatch.setattr(
        "app.modules.semantic_retrieval.cohere_rerank.cohere_rerank_chunks",
        _raise_cohere,
    )
    monkeypatch.setattr(semantic_service, "embed_query", lambda query: [1.0, 0.0])
    monkeypatch.setattr(
        semantic_service,
        "embed_documents",
        lambda texts: [[0.0, 1.0], [1.0, 0.0]],
    )

    reranked = semantic_service.rerank_evidence_chunks("renal potassium", _chunks(), top_k=2)

    assert [chunk.chunk_id for chunk in reranked] == ["strong", "weak"]
    assert reranked[0].metadata["rerank_provider"] == "bi_encoder"


def test_retrieval_candidate_count_defaults_to_fifty(monkeypatch) -> None:
    monkeypatch.setattr(settings, "semantic_rerank_candidates", 50)
    assert semantic_service.retrieval_candidate_count(8) == 50
