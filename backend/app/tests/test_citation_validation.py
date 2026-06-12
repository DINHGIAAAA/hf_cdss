from app.modules.citation_validation.service import source_link_for_chunk, validate_citations
from app.modules.reasoning.service import build_recommendation
from app.schemas.graphrag import EvidenceChunk, GraphRAGContextResponse
from app.schemas.patient import PatientProfile
from app.schemas.recommendation import RecommendationRequest


def test_source_link_adds_pdf_page_fragment() -> None:
    chunk = EvidenceChunk(
        chunk_id="c1",
        document_id="guideline",
        source_type="guideline",
        section="MRA",
        text="MRA potassium renal monitoring.",
        score=1.0,
        metadata={"source_url": "https://example.org/hf.pdf", "page": 42},
        source_url="https://example.org/hf.pdf",
        page=42,
    )

    assert source_link_for_chunk(chunk) == "https://example.org/hf.pdf#page=42"


def test_validate_citations_marks_supported_items() -> None:
    patient = PatientProfile(
        case_id="CITATION_CASE",
        lvef=30,
        egfr=25,
        potassium=5.6,
        systolic_bp=104,
        heart_rate=70,
        comorbidities=["CKD"],
        current_medications=["spironolactone"],
        allergies=["no known drug allergies"],
    )
    recommendation = build_recommendation(RecommendationRequest(patient=patient))
    context = GraphRAGContextResponse(
        case_id=patient.case_id,
        query_terms=["mra", "potassium", "renal"],
        graph_facts=[],
        evidence_chunks=[
            EvidenceChunk(
                chunk_id="mra_guideline_chunk",
                document_id="aha_acc_hfsa_2022_hf_guideline",
                source_type="guideline",
                section="MRA",
                text="Mineralocorticoid receptor antagonist therapy requires renal function and potassium monitoring and may be avoided with hyperkalemia.",
                score=10,
                metadata={
                    "source_id": "aha_acc_hfsa_2022_hf_guideline",
                    "source_url": "https://example.org/hf.pdf",
                    "page": 77,
                    "citation": "AHA ACC HFSA guideline.",
                },
                source_url="https://example.org/hf.pdf",
                page=77,
            )
        ],
        context_summary="test context",
        retrieval_sources=["local_chunks"],
    )

    validation = validate_citations(recommendation, context)

    assert validation.supports
    assert any(item.target_type == "constraint" for item in validation.supports)
    assert any("mra_guideline_chunk" in item.evidence_refs for item in validation.supports)
    assert any("https://example.org/hf.pdf#page=77" in item.source_links for item in validation.supports)
    assert any(item.evidence_verdict in {"supported", "weakly_supported"} for item in validation.supports)
    assert any((item.confidence or 0) > 0 for item in validation.supports)
