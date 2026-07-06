from app.core.config import settings
from app.modules.semantic_retrieval import service as semantic_service
from app.schemas.graphrag import EvidenceChunk


def test_embedding_index_version_includes_provider_model_and_dimensions(monkeypatch) -> None:
    monkeypatch.setattr(settings, "embedding_provider", "ollama")
    monkeypatch.setattr(settings, "embedding_model", "nomic-embed-text")
    monkeypatch.setattr(settings, "embedding_dimensions", 768)

    assert semantic_service.embedding_index_version() == "ollama_nomic_embed_text_768"


def test_reciprocal_rank_fusion_merges_rank_lists() -> None:
    left = EvidenceChunk(
        chunk_id="left",
        document_id="a",
        source_type="guideline",
        section="A",
        text="Left chunk.",
        score=0.2,
    )
    right = EvidenceChunk(
        chunk_id="right",
        document_id="b",
        source_type="guideline",
        section="B",
        text="Right chunk.",
        score=0.9,
    )
    merged = semantic_service.reciprocal_rank_fusion([[left], [right, left]])
    assert merged[0].chunk_id == "left"


def test_semantic_rerank_orders_by_embedding_similarity(monkeypatch) -> None:
    monkeypatch.setattr(settings, "semantic_rerank_enabled", True)
    monkeypatch.setattr(settings, "semantic_rerank_provider", "bi_encoder")
    monkeypatch.setattr(settings, "semantic_rerank_weight", 1.0)
    monkeypatch.setattr(semantic_service, "embed_query", lambda query: [1.0, 0.0])
    monkeypatch.setattr(
        semantic_service,
        "embed_documents",
        lambda texts: [[0.0, 1.0], [1.0, 0.0]],
    )
    weak = EvidenceChunk(
        chunk_id="weak",
        document_id="a",
        source_type="drug_label",
        section="DOSAGE",
        text="Unrelated dose text.",
        score=0.95,
    )
    strong = EvidenceChunk(
        chunk_id="strong",
        document_id="b",
        source_type="guideline",
        section="RENAL",
        text="Renal potassium monitoring for MRA therapy.",
        score=0.1,
    )

    reranked = semantic_service.rerank_evidence_chunks("renal potassium", [weak, strong], top_k=2)

    assert [chunk.chunk_id for chunk in reranked] == ["strong", "weak"]
    assert reranked[0].score == 1.0

