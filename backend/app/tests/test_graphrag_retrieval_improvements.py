import asyncio

from app.core.config import settings
from app.modules.datastores import chroma as chroma_module
from app.modules.graphrag import service as graphrag_service
from app.modules.graphrag.evidence_scope import EvidenceScope
from app.modules.graphrag.service import (
    adaptive_top_k,
    build_graphrag_context,
    build_graphrag_context_async,
    expand_chunk_windows,
)
from app.modules.semantic_retrieval import service as semantic_service
from app.schemas.graphrag import EvidenceChunk, GraphRAGContextRequest
from app.schemas.patient import PatientProfile


def _patient(**overrides) -> PatientProfile:
    base = {
        "case_id": "CASE_RETRIEVAL",
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


def _chunk(chunk_id: str, score: float) -> EvidenceChunk:
    return EvidenceChunk(
        chunk_id=chunk_id,
        document_id="doc",
        source_type="guideline",
        section="RENAL",
        text=f"Evidence for {chunk_id}",
        score=score,
    )


def test_lost_in_middle_reorder_places_best_chunks_at_edges() -> None:
    chunks = [f"c{i}" for i in range(5)]

    reordered = semantic_service.lost_in_middle_reorder(chunks)

    assert reordered == ["c0", "c2", "c4", "c3", "c1"]


def test_reorder_evidence_chunks_for_llm_respects_setting(monkeypatch) -> None:
    chunks = [
        EvidenceChunk(
            chunk_id=f"c{i}",
            document_id="doc",
            source_type="guideline",
            section="RENAL",
            text=f"chunk {i}",
            score=1.0 - (i * 0.1),
        )
        for i in range(4)
    ]

    monkeypatch.setattr(settings, "graphrag_lost_in_middle_reorder_enabled", False)
    assert semantic_service.reorder_evidence_chunks_for_llm(chunks) == chunks

    monkeypatch.setattr(settings, "graphrag_lost_in_middle_reorder_enabled", True)
    reordered = semantic_service.reorder_evidence_chunks_for_llm(chunks)
    assert reordered[0].chunk_id == "c0"
    assert reordered[-1].chunk_id == "c1"


def test_reciprocal_rank_fusion_prefers_consensus_ranking() -> None:
    list_a = [_chunk("a", 0.9), _chunk("b", 0.8), _chunk("c", 0.7)]
    list_b = [_chunk("b", 0.6), _chunk("a", 0.5), _chunk("d", 0.4)]

    merged = semantic_service.reciprocal_rank_fusion([list_a, list_b])

    assert [chunk.chunk_id for chunk in merged[:2]] == ["a", "b"]


def test_adaptive_top_k_scales_with_clinical_complexity(monkeypatch) -> None:
    monkeypatch.setattr(settings, "graphrag_adaptive_top_k", True)
    request = GraphRAGContextRequest(
        patient=_patient(),
        top_k=6,
        clinical_state={
            "focus_medication_classes": ["mra", "sglt2i"],
            "conditions": ["ckd", "diabetes"],
            "mentioned_medications": [{"name": "spironolactone"}],
        },
    )

    assert adaptive_top_k(request) == 12


def test_contextual_prefix_prepends_document_context() -> None:
    chunk = {
        "document_id": "kdigo_2024_ckd_guideline",
        "source_type": "guideline",
        "section": "MRA use in CKD",
        "text": "eGFR below 30 mL/min requires caution.",
        "metadata": {"publisher": "KDIGO"},
    }

    embed_text = chroma_module._embed_text_for_chunk(chunk)

    assert embed_text.startswith("[From kdigo 2024 ckd guideline, MRA use in CKD, KDIGO, guideline]:")
    assert "below 30" in embed_text


def test_expand_chunk_windows_adds_neighbors(monkeypatch) -> None:
    monkeypatch.setattr(
        graphrag_service,
        "load_published_chunks",
        lambda: [
            {
                "chunk_id": "doc__renal__0001__abc",
                "document_id": "doc",
                "source_type": "guideline",
                "section": "RENAL",
                "section_id": "doc__renal",
                "text": "First chunk text.",
                "metadata": {"section_id": "doc__renal", "chunk_index": 1, "chunk_count": 3},
            },
            {
                "chunk_id": "doc__renal__0002__def",
                "document_id": "doc",
                "source_type": "guideline",
                "section": "RENAL",
                "section_id": "doc__renal",
                "text": "Second chunk text.",
                "metadata": {"section_id": "doc__renal", "chunk_index": 2, "chunk_count": 3},
            },
            {
                "chunk_id": "doc__renal__0003__ghi",
                "document_id": "doc",
                "source_type": "guideline",
                "section": "RENAL",
                "section_id": "doc__renal",
                "text": "Third chunk text.",
                "metadata": {"section_id": "doc__renal", "chunk_index": 3, "chunk_count": 3},
            },
        ],
    )
    graphrag_service._chunk_index_by_id.cache_clear()
    graphrag_service._chunk_index_by_position.cache_clear()

    anchor = EvidenceChunk(
        chunk_id="doc__renal__0002__def",
        document_id="doc",
        source_type="guideline",
        section="RENAL",
        text="Second chunk text.",
        score=0.9,
        metadata={"section_id": "doc__renal", "chunk_index": 2, "chunk_count": 3},
    )

    expanded = expand_chunk_windows([anchor], window_size=1)

    assert {chunk.chunk_id for chunk in expanded} == {
        "doc__renal__0001__abc",
        "doc__renal__0002__def",
        "doc__renal__0003__ghi",
    }


def test_build_graphrag_context_sync_uses_hyde_when_loop_running(monkeypatch) -> None:
    monkeypatch.setattr(settings, "hyde_retrieval_enabled", True)
    monkeypatch.setattr(settings, "llm_api_type", "chat_completions")
    monkeypatch.setattr(settings, "retrieval_backend", "databases")
    captured: dict[str, list[str]] = {"queries": []}

    async def fake_hyde(*_args, **_kwargs):
        return "Mineralocorticoid receptor antagonists require potassium monitoring."

    def fake_multi_query(queries: list[str], top_k: int, **kwargs):
        captured["queries"] = queries
        return [
            EvidenceChunk(
                chunk_id="chunk-1",
                document_id="doc",
                source_type="guideline",
                section="RENAL",
                text="Potassium monitoring guidance.",
                score=0.8,
            )
        ]

    monkeypatch.setattr("app.modules.graphrag.service.generate_hyde_document", fake_hyde)
    monkeypatch.setattr("app.modules.graphrag.service._retrieve_evidence_from_chroma", fake_multi_query)
    monkeypatch.setattr("app.modules.graphrag.service.resolve_evidence_scope", lambda *_args, **_kwargs: EvidenceScope())
    monkeypatch.setattr("app.modules.graphrag.service.retrieve_neo4j", lambda *_args, **_kwargs: [])
    monkeypatch.setattr("app.modules.graphrag.service.retrieve_graph_facts", lambda *_args, **_kwargs: [])
    monkeypatch.setattr("app.modules.graphrag.service.retrieve_evidence_chunks", lambda *_args, **_kwargs: [])

    async def run_in_loop() -> None:
        response = build_graphrag_context(
            GraphRAGContextRequest(
                patient=_patient(),
                query="co nen tiep spiro k+ 5.7",
                top_k=4,
            )
        )
        assert response.hyde_used is True
        assert any("Mineralocorticoid receptor antagonists" in query for query in captured["queries"])

    asyncio.run(run_in_loop())


def test_build_graphrag_context_async_uses_multi_query(monkeypatch) -> None:
    monkeypatch.setattr(settings, "hyde_retrieval_enabled", True)
    monkeypatch.setattr(settings, "graphrag_multi_query_enabled", True)
    monkeypatch.setattr(settings, "retrieval_backend", "databases")
    captured: dict[str, list[str]] = {"queries": []}

    async def fake_hyde(*_args, **_kwargs):
        return "HyDE document about potassium and renal function."

    def fake_multi_query(queries: list[str], top_k: int, **kwargs):
        captured["queries"] = queries
        return [
            EvidenceChunk(
                chunk_id="chunk-1",
                document_id="doc",
                source_type="guideline",
                section="RENAL",
                text="Potassium monitoring guidance.",
                score=0.8,
            )
        ]

    monkeypatch.setattr("app.modules.graphrag.service.generate_hyde_document", fake_hyde)
    monkeypatch.setattr("app.modules.graphrag.service._retrieve_evidence_from_chroma", fake_multi_query)
    monkeypatch.setattr("app.modules.graphrag.service.resolve_evidence_scope", lambda *_args, **_kwargs: EvidenceScope())
    monkeypatch.setattr("app.modules.graphrag.service.retrieve_neo4j", lambda *_args, **_kwargs: [])
    monkeypatch.setattr("app.modules.graphrag.service.retrieve_graph_facts", lambda *_args, **_kwargs: [])
    monkeypatch.setattr("app.modules.graphrag.service.expand_chunk_windows", lambda chunks, **kwargs: chunks)

    response = asyncio.run(
        build_graphrag_context_async(
            GraphRAGContextRequest(
                patient=_patient(),
                query="co nen tiep spiro k+ 5.7",
                top_k=4,
                clinical_state={"conditions": ["ckd"], "focus_medication_classes": ["mra"]},
            )
        )
    )

    assert response.hyde_used is True
    assert len(captured["queries"]) >= 2
    assert "multi_query" in response.retrieval_sources
