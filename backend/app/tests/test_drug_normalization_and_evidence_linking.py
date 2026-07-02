import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.modules.drug_normalization.service import (
    expand_drug_search_terms,
    normalize_drug_name,
    resolve_pipeline_drug_id,
)
from app.modules.evidence_linking.service import enrich_recommendation_evidence, prioritize_context_chunks
from app.schemas.clinical import Constraint
from app.schemas.graphrag import EvidenceChunk, GraphRAGContextResponse
from app.schemas.recommendation import MedicationRecommendation, RecommendationResponse
from scraper.process.drug_normalization import resolve_pipeline_drug_id as scraper_resolve_drug
from scraper.process.evidence_linking import find_chunk_for_claim


def test_normalize_brand_names_to_pipeline_ids() -> None:
    assert resolve_pipeline_drug_id("Jardiance") == "empagliflozin"
    assert resolve_pipeline_drug_id("entresto") == "sacubitril_and_valsartan"
    assert scraper_resolve_drug("jardiance") == "empagliflozin"


def test_expand_drug_search_terms_includes_brand_and_generic() -> None:
    terms = expand_drug_search_terms("entresto")
    assert "entresto" in terms
    assert "sacubitril_and_valsartan" in terms or "sacubitril/valsartan" in terms


def test_find_chunk_for_claim_matches_document_and_text() -> None:
    claim = {
        "document_id": "empagliflozin",
        "source_section": "CONTRAINDICATIONS",
        "evidence": "Empagliflozin is contraindicated in patients with severe renal impairment and dialysis.",
    }
    chunks = [
        {
            "chunk_id": "empagliflozin__contraindications__0001__abc12345",
            "document_id": "empagliflozin",
            "section": "CONTRAINDICATIONS",
            "text": "Empagliflozin is contraindicated in patients with severe renal impairment and dialysis.",
        }
    ]
    matched = find_chunk_for_claim(claim, chunks)
    assert matched is not None
    assert matched["chunk_id"].startswith("empagliflozin__")


def test_enrich_recommendation_evidence_uses_constraint_chunk_ids() -> None:
    response = RecommendationResponse(
        case_id="case-1",
        patient_summary={},
        risk_flags=[],
        constraints=[
            Constraint(
                constraint_id="case-1:rule-1",
                case_id="case-1",
                target_drug_class="empagliflozin",
                action="avoid",
                reason="Renal safety constraint",
                evidence_ref="empagliflozin__warnings__0001__deadbeef",
            )
        ],
        recommendations=[
            MedicationRecommendation(
                drug_class="SGLT2 inhibitor",
                status="consider_with_caution",
                rationale="Review SGLT2 use",
                constraint_ids=["case-1:rule-1"],
            )
        ],
        overall_status="approved_with_warnings",
        disclaimer="demo",
    )
    enriched = enrich_recommendation_evidence(response)
    assert "empagliflozin__warnings__0001__deadbeef" in enriched.recommendations[0].evidence


def test_prioritize_context_chunks_puts_linked_chunks_first() -> None:
    context = GraphRAGContextResponse(
        case_id="case-1",
        query_terms=["empagliflozin"],
        graph_facts=[],
        evidence_chunks=[
            EvidenceChunk(
                chunk_id="other_chunk",
                document_id="other",
                source_type="guideline",
                text="generic text",
                score=0.5,
            ),
            EvidenceChunk(
                chunk_id="linked_chunk",
                document_id="empagliflozin",
                source_type="drug_label",
                text="linked text",
                score=0.9,
            ),
        ],
        context_summary="demo",
    )
    prioritized = prioritize_context_chunks(context, ["linked_chunk"])
    assert prioritized.evidence_chunks[0].chunk_id == "linked_chunk"
