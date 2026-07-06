"""Link recommendations and constraints to indexed evidence chunks."""

from __future__ import annotations

from functools import lru_cache

from app.modules.citation_validation.service import source_link_for_chunk
from app.modules.graphrag.service import load_chunks
from app.modules.semantic_retrieval.service import reorder_evidence_chunks_for_llm
from app.schemas.clinical import Constraint
from app.schemas.graphrag import CitationValidation, EvidenceChunk, GraphRAGContextResponse
from app.schemas.recommendation import MedicationRecommendation, RecommendationResponse


def _is_chunk_id(value: str | None) -> bool:
    if not value:
        return False
    if value.startswith(("week3_", "rule:", "constraint:", "risk:")):
        return False
    return "__" in value or value.startswith("chunk_")


@lru_cache(maxsize=1)
def _chunk_index() -> dict[str, dict]:
    return {chunk["chunk_id"]: chunk for chunk in load_chunks() if chunk.get("chunk_id")}


def chunk_by_id(chunk_id: str) -> dict | None:
    return _chunk_index().get(chunk_id)


def evidence_chunk_from_record(record: dict) -> EvidenceChunk:
    metadata = record.get("metadata") or {}
    chunk = EvidenceChunk(
        chunk_id=record["chunk_id"],
        document_id=record.get("document_id", ""),
        source_type=record.get("source_type", ""),
        section=record.get("section"),
        text=record.get("text", "")[:900],
        score=1.0,
        metadata=metadata,
        source_url=metadata.get("source_url"),
        page=metadata.get("page") or metadata.get("page_start"),
    )
    return chunk.model_copy(update={"source_link": source_link_for_chunk(chunk)})


def hydrate_constraint(constraint: Constraint, rule_metadata: dict | None = None) -> Constraint:
    metadata = rule_metadata or {}
    source_locator = metadata.get("source_locator")
    chunk_id = constraint.evidence_ref if _is_chunk_id(constraint.evidence_ref) else metadata.get("chunk_id")
    if not source_locator and chunk_id:
        record = chunk_by_id(chunk_id)
        if record:
            metadata = record.get("metadata") or {}
            source_locator = metadata.get("source_locator") or metadata.get("source_url")
    return constraint.model_copy(
        update={
            "evidence_ref": chunk_id or constraint.evidence_ref,
            "source_locator": source_locator,
        }
    )


def collect_constraint_chunk_ids(response: RecommendationResponse) -> list[str]:
    chunk_ids: list[str] = []
    for constraint in response.constraints:
        if _is_chunk_id(constraint.evidence_ref):
            chunk_ids.append(constraint.evidence_ref)
    return chunk_ids


def enrich_recommendation_evidence(
    response: RecommendationResponse,
    citation_validation: CitationValidation | None = None,
) -> RecommendationResponse:
    supports_by_target = {}
    if citation_validation:
        supports_by_target = {
            support.target_id: support for support in citation_validation.supports if support.target_type == "recommendation"
        }

    recommendations: list[MedicationRecommendation] = []
    for item in response.recommendations:
        refs: list[str] = []
        for ref in item.evidence:
            if _is_chunk_id(ref):
                refs.append(ref)
        for constraint_id in item.constraint_ids:
            constraint = next((c for c in response.constraints if c.constraint_id == constraint_id), None)
            if constraint and _is_chunk_id(constraint.evidence_ref):
                refs.append(constraint.evidence_ref)
        support = supports_by_target.get(item.drug_class)
        if support:
            refs.extend(ref for ref in support.evidence_refs if _is_chunk_id(ref))
        unique_refs = list(dict.fromkeys(refs))
        recommendations.append(item.model_copy(update={"evidence": unique_refs}))
    return response.model_copy(update={"recommendations": recommendations})


def prioritize_context_chunks(
    context: GraphRAGContextResponse,
    chunk_ids: list[str],
) -> GraphRAGContextResponse:
    if not chunk_ids:
        return context

    prioritized: list[EvidenceChunk] = []
    seen: set[str] = set()
    by_id = {chunk.chunk_id: chunk for chunk in context.evidence_chunks}

    for chunk_id in chunk_ids:
        if chunk_id in seen:
            continue
        if chunk_id in by_id:
            prioritized.append(by_id[chunk_id])
            seen.add(chunk_id)
            continue
        record = chunk_by_id(chunk_id)
        if record:
            prioritized.append(evidence_chunk_from_record(record))
            seen.add(chunk_id)

    for chunk in context.evidence_chunks:
        if chunk.chunk_id not in seen:
            prioritized.append(chunk)
            seen.add(chunk.chunk_id)

    return context.model_copy(
        update={"evidence_chunks": reorder_evidence_chunks_for_llm(prioritized[:12])}
    )


def attach_linked_evidence(
    response: RecommendationResponse,
    context: GraphRAGContextResponse,
    citation_validation: CitationValidation | None = None,
) -> tuple[RecommendationResponse, GraphRAGContextResponse]:
    enriched = enrich_recommendation_evidence(response, citation_validation)
    chunk_ids = collect_constraint_chunk_ids(enriched)
    for item in enriched.recommendations:
        chunk_ids.extend(ref for ref in item.evidence if _is_chunk_id(ref))
    prioritized_context = prioritize_context_chunks(context, list(dict.fromkeys(chunk_ids)))
    return enriched, prioritized_context
