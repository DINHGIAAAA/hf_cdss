from app.modules.graphrag.evidence_scope import (
    EvidenceScope,
    merge_evidence_scopes,
    resolve_evidence_scope_from_facts,
)
from app.schemas.graphrag import GraphFact


def test_evidence_scope_chroma_where_or_clause() -> None:
    scope = EvidenceScope(
        document_ids=("kdigo_2024_ckd_guideline",),
        section_ids=("abc123",),
    )
    where = scope.chroma_where()
    assert where == {
        "$or": [
            {"document_id": {"$in": ["kdigo_2024_ckd_guideline"]}},
            {"section_id": {"$in": ["abc123"]}},
        ]
    }


def test_resolve_evidence_scope_from_facts_parses_graph_nodes() -> None:
    facts = [
        GraphFact(
            fact_id="rel_1",
            source_id="chunk:doc__renal__0001__abc",
            source_type="Chunk",
            relationship_type="PART_OF",
            target_id="section:sec123",
            target_type="Section",
            metadata={"document_id": "kdigo_2024_ckd_guideline", "section_id": "sec123"},
        )
    ]

    scope = resolve_evidence_scope_from_facts(facts)

    assert "doc__renal__0001__abc" in scope.chunk_ids
    assert "sec123" in scope.section_ids
    assert "kdigo_2024_ckd_guideline" in scope.document_ids


def test_merge_evidence_scopes_deduplicates() -> None:
    merged = merge_evidence_scopes(
        EvidenceScope(document_ids=("doc_a",)),
        EvidenceScope(document_ids=("doc_a", "doc_b"), section_ids=("sec1",)),
    )
    assert merged.document_ids == ("doc_a", "doc_b")
    assert merged.section_ids == ("sec1",)


def test_graphrag_uses_graph_guided_scope(monkeypatch) -> None:
    import asyncio

    from app.core.config import settings
    from app.modules.graphrag.service import build_graphrag_context_async
    from app.schemas.graphrag import GraphRAGContextRequest
    from app.schemas.patient import PatientProfile
    from app.modules.graphrag.evidence_scope import EvidenceScope

    monkeypatch.setattr(settings, "retrieval_backend", "databases")
    monkeypatch.setattr(settings, "graphrag_graph_guided_filter_enabled", True)
    monkeypatch.setattr(settings, "graphrag_multi_query_enabled", False)
    monkeypatch.setattr(settings, "hyde_retrieval_enabled", False)

    captured: dict[str, object] = {}

    def fake_scope(terms, *, top_k=24, chunk_ids=None):
        return EvidenceScope(document_ids=("spironolactone_label",))

    def fake_chroma(query, top_k, *, scope=None):
        captured["scope"] = scope
        return []

    monkeypatch.setattr("app.modules.graphrag.service.resolve_evidence_scope", fake_scope)
    monkeypatch.setattr("app.modules.graphrag.service.retrieve_chroma", fake_chroma)
    monkeypatch.setattr("app.modules.graphrag.service.retrieve_neo4j", lambda *_args, **_kwargs: [])
    monkeypatch.setattr("app.modules.graphrag.service.retrieve_graph_facts", lambda *_args, **_kwargs: [])
    monkeypatch.setattr("app.modules.graphrag.service.retrieve_evidence_chunks", lambda *_args, **_kwargs: [])

    response = asyncio.run(
        build_graphrag_context_async(
            GraphRAGContextRequest(
                patient=PatientProfile(case_id="CASE_SCOPE"),
                query="mra hyperkalemia spironolactone",
                top_k=4,
            )
        )
    )

    assert captured["scope"] is not None
    assert captured["scope"].document_ids == ("spironolactone_label",)
    assert "graph_guided" in response.retrieval_sources
