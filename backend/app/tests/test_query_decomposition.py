from app.core.config import settings
from app.modules.graphrag.query_decomposition import (
    collect_condition_facets,
    collect_drug_class_facets,
    decompose_retrieval_queries,
    should_decompose_query,
)
from app.modules.graphrag.service import _semantic_retrieval_queries
from app.schemas.graphrag import GraphRAGContextRequest
from app.tests.conftest import hfref_patient


def test_should_decompose_for_multiple_drug_classes() -> None:
    facets = collect_drug_class_facets(
        hfref_patient(
            comorbidities=["CKD", "diabetes"],
            current_medications=["spironolactone", "empagliflozin"],
        ),
        {
            "focus_medication_classes": ["MRA", "SGLT2i"],
            "mentioned_medications": [
                {"name": "spironolactone", "drug_class": "MRA"},
                {"name": "empagliflozin", "drug_class": "SGLT2i"},
            ],
        },
    )
    conditions = collect_condition_facets(hfref_patient(), {"conditions": ["CKD", "diabetes"]})

    assert len(facets) >= 2
    assert should_decompose_query(facets, conditions) is True


def test_decompose_generates_per_drug_class_and_comorbidity_queries() -> None:
    patient = hfref_patient(
        comorbidities=["CKD", "diabetes"],
        current_medications=["spironolactone", "empagliflozin"],
    )
    clinical_state = {
        "intent": "safety_check",
        "hf_type": "HFrEF",
        "focus_medication_classes": ["MRA", "SGLT2i"],
        "conditions": ["CKD", "diabetes"],
        "mentioned_medications": [
            {"name": "spironolactone", "drug_class": "MRA"},
            {"name": "empagliflozin", "drug_class": "SGLT2i"},
        ],
    }
    request = GraphRAGContextRequest(
        patient=patient,
        query="Can I continue spironolactone and empagliflozin with CKD and diabetes?",
        clinical_state=clinical_state,
    )

    queries = decompose_retrieval_queries(request, baseline_query=request.query or "")

    assert len(queries) >= 4
    assert any("mineralocorticoid" in query.lower() and "spironolactone" in query.lower() for query in queries)
    assert any("sglt2" in query.lower() and "empagliflozin" in query.lower() for query in queries)
    assert any("diabetes" in query.lower() for query in queries)
    assert any("ckd" in query.lower() or "renal" in query.lower() for query in queries)


def test_decompose_skipped_for_simple_single_drug_case() -> None:
    patient = hfref_patient(
        current_medications=["spironolactone"],
        comorbidities=[],
        egfr=70,
        potassium=4.2,
        systolic_bp=120,
        heart_rate=72,
    )
    request = GraphRAGContextRequest(
        patient=patient,
        query="Is spironolactone safe?",
        clinical_state={
            "focus_medication_classes": ["MRA"],
            "conditions": [],
            "mentioned_medications": [{"name": "spironolactone", "drug_class": "MRA"}],
        },
    )

    assert decompose_retrieval_queries(request, baseline_query=request.query or "") == []


def test_semantic_retrieval_queries_include_decomposed_facets(monkeypatch) -> None:
    monkeypatch.setattr(settings, "graphrag_multi_query_enabled", True)
    monkeypatch.setattr(settings, "graphrag_query_decomposition_enabled", True)

    request = GraphRAGContextRequest(
        patient=hfref_patient(),
        query="Review MRA and SGLT2i safety with CKD",
        clinical_state={
            "intent": "safety_check",
            "hf_type": "HFrEF",
            "focus_medication_classes": ["MRA", "SGLT2i"],
            "conditions": ["CKD", "diabetes"],
            "mentioned_medications": [
                {"name": "spironolactone", "drug_class": "MRA"},
                {"name": "empagliflozin", "drug_class": "SGLT2i"},
            ],
        },
    )

    queries, decomposed = _semantic_retrieval_queries(
        request,
        baseline_query=request.query or "",
        hyde_document=None,
    )

    assert decomposed is True
    assert len(queries) >= 5
    assert any("sglt2" in query.lower() for query in queries)
    assert any("mineralocorticoid" in query.lower() for query in queries)


def test_build_graphrag_context_marks_query_decomposition_source(monkeypatch) -> None:
    import asyncio

    from app.modules.graphrag.service import build_graphrag_context_async

    monkeypatch.setattr(settings, "hyde_retrieval_enabled", False)
    monkeypatch.setattr(settings, "graphrag_multi_query_enabled", True)
    monkeypatch.setattr(settings, "graphrag_query_decomposition_enabled", True)
    monkeypatch.setattr(settings, "retrieval_backend", "databases")

    def fake_chroma_candidates(queries: list[str], pool_k: int, **kwargs):
        return []

    monkeypatch.setattr("app.modules.graphrag.service._fetch_chroma_candidates", fake_chroma_candidates)
    monkeypatch.setattr("app.modules.graphrag.service.retrieve_bm25_evidence_chunks", lambda *_args, **_kwargs: [])
    monkeypatch.setattr("app.modules.graphrag.service.resolve_evidence_scope", lambda *_args, **_kwargs: None)
    monkeypatch.setattr("app.modules.graphrag.service.retrieve_neo4j", lambda *_args, **_kwargs: [])
    monkeypatch.setattr("app.modules.graphrag.service.retrieve_graph_facts", lambda *_args, **_kwargs: [])
    monkeypatch.setattr("app.modules.graphrag.service.expand_chunk_windows", lambda chunks, **kwargs: chunks)

    response = asyncio.run(
        build_graphrag_context_async(
            GraphRAGContextRequest(
                patient=hfref_patient(),
                query="Review MRA and SGLT2i with CKD and diabetes",
                top_k=4,
                clinical_state={
                    "intent": "safety_check",
                    "hf_type": "HFrEF",
                    "focus_medication_classes": ["MRA", "SGLT2i"],
                    "conditions": ["CKD", "diabetes"],
                    "mentioned_medications": [
                        {"name": "spironolactone", "drug_class": "MRA"},
                        {"name": "empagliflozin", "drug_class": "SGLT2i"},
                    ],
                },
            )
        )
    )

    assert "query_decomposition" in response.retrieval_sources
