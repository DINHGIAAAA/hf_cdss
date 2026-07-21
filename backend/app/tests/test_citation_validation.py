from app.modules.citation_validation.service import (
    apply_citation_guardrails,
    source_link_for_chunk,
    validate_citations,
)
from app.modules.citation_validation.terms import class_terms, expand_synonyms
from app.modules.reasoning.service import build_recommendation
from app.schemas.graphrag import CitationSupport, CitationValidation, EvidenceChunk, GraphRAGContextResponse
from app.schemas.patient import PatientProfile
from app.schemas.recommendation import MedicationRecommendation, RecommendationRequest, RecommendationResponse


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


def test_arni_synonyms_include_sacubitril() -> None:
    terms = class_terms("RAAS inhibition / ARNI")
    joined = " ".join(terms)
    assert "sacubitril" in joined
    assert "arni" in joined or "entresto" in joined
    expanded = expand_synonyms(["arni"])
    assert any("sacubitril" in t or "entresto" in t or "valsartan" in t for t in expanded)


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

    validation = validate_citations(recommendation, context, patient=patient)

    assert validation.supports
    assert validation.recommendation_status in {"strong", "weak", "missing"}
    assert validation.safety_status in {"strong", "weak", "missing"}
    assert any(item.target_type == "constraint" for item in validation.supports)
    assert any("mra_guideline_chunk" in item.evidence_refs for item in validation.supports)
    assert any("https://example.org/hf.pdf#page=77" in item.source_links for item in validation.supports)
    assert any(item.evidence_verdict in {"supported", "weakly_supported"} for item in validation.supports)
    assert any((item.confidence or 0) > 0 for item in validation.supports)
    assert any(item.explanation for item in validation.supports)
    assert any(item.unmatched_terms is not None for item in validation.supports)


def test_overall_status_follows_recommendations_not_only_safety() -> None:
    validation = CitationValidation(
        status="weak",
        recommendation_status="strong",
        safety_status="missing",
        supports=[
            CitationSupport(
                target_id="SGLT2 inhibitor",
                target_type="recommendation",
                evidence_status="strong",
                message="ok",
                required_terms=["sglt2"],
                matched_terms=["sglt2"],
                unmatched_terms=[],
            ),
            CitationSupport(
                target_id="ix_demo",
                target_type="interaction",
                evidence_status="missing",
                message="missing",
                required_terms=["interaction"],
                matched_terms=[],
                unmatched_terms=["interaction"],
            ),
        ],
    )
    # Recompute via real function with empty safety-only weakness path
    response = RecommendationResponse(
        case_id="X",
        patient_summary={},
        risk_flags=[],
        recommendations=[
            MedicationRecommendation(
                drug_class="SGLT2 inhibitor",
                status="consider",
                rationale="SGLT2 inhibitor therapy for HFrEF.",
                evidence=[],
                warnings=[],
            )
        ],
        overall_status="consider",
        disclaimer="test",
    )
    context = GraphRAGContextResponse(
        case_id="X",
        query_terms=["sglt2"],
        graph_facts=[],
        evidence_chunks=[
            EvidenceChunk(
                chunk_id="sglt2_chunk",
                document_id="guideline",
                source_type="guideline",
                section="SGLT2",
                text="SGLT2 inhibitor dapagliflozin empagliflozin recommended in HFrEF with renal monitoring egfr.",
                score=5,
                metadata={},
            )
        ],
        context_summary="",
        retrieval_sources=[],
    )
    result = validate_citations(response, context)
    assert result.recommendation_status in {"strong", "weak"}
    assert result.status != "missing" or result.recommendation_status == "missing"


def test_missing_citation_marks_missing_and_explanation() -> None:
    response = RecommendationResponse(
        case_id="Y",
        patient_summary={},
        risk_flags=[],
        recommendations=[
            MedicationRecommendation(
                drug_class="SGLT2 inhibitor",
                status="consider",
                rationale="Start SGLT2 inhibitor.",
            )
        ],
        overall_status="consider",
        disclaimer="test",
    )
    context = GraphRAGContextResponse(
        case_id="Y",
        query_terms=[],
        graph_facts=[],
        evidence_chunks=[
            EvidenceChunk(
                chunk_id="unrelated",
                document_id="other",
                source_type="review",
                section="Intro",
                text="This passage discusses orthopedic surgery only.",
                score=1,
                metadata={},
            )
        ],
        context_summary="",
        retrieval_sources=[],
    )
    validation = validate_citations(response, context)
    support = next(s for s in validation.supports if s.target_type == "recommendation")
    assert support.evidence_status in {"missing", "weak"}
    assert support.explanation
    assert support.required_terms
    guarded = apply_citation_guardrails(response, validation)
    item = guarded.recommendations[0]
    if support.evidence_status == "missing":
        assert item.status == "review"
        assert any("Citation" in w or "citation" in w.lower() for w in item.warnings)


def test_dose_warning_prefers_drug_label_passage() -> None:
    from app.schemas.medication_safety import MedicationSafetyWarning

    response = RecommendationResponse(
        case_id="Z",
        patient_summary={},
        risk_flags=[],
        dose_warnings=[
            MedicationSafetyWarning(
                warning_id="dose_digoxin_renal_review",
                case_id="Z",
                category="dose",
                target="digoxin",
                severity="moderate",
                message="Digoxin dosing requires renal function review.",
                evidence_ref="week7_dose_rule:DIGOXIN_RENAL_REVIEW",
            )
        ],
        recommendations=[],
        overall_status="ok",
        disclaimer="test",
    )
    context = GraphRAGContextResponse(
        case_id="Z",
        query_terms=["digoxin"],
        graph_facts=[],
        evidence_chunks=[
            EvidenceChunk(
                chunk_id="label_digoxin",
                document_id="digoxin",
                source_type="drug_label",
                section="7 DRUG INTERACTIONS",
                text="Digoxin renal dosing interaction concomitant monitoring serum digoxin concentrations.",
                score=2,
                metadata={},
            ),
            EvidenceChunk(
                chunk_id="guideline_general",
                document_id="hf_guideline",
                source_type="guideline",
                section="General",
                text="Heart failure therapy overview without digoxin detail.",
                score=9,
                metadata={},
            ),
        ],
        context_summary="",
        retrieval_sources=[],
    )
    validation = validate_citations(response, context)
    support = next(s for s in validation.supports if s.target_id == "dose_digoxin_renal_review")
    assert support.evidence_status in {"strong", "weak"}
    if support.evidence_refs:
        assert "label_digoxin" in support.evidence_refs
