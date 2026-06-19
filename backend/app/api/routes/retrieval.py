from fastapi import APIRouter, Query

from app.modules.graphrag.service import search_evidence
from app.schemas.graphrag import EvidenceSearchResponse
from app.schemas.retrieval import RetrievalContextRequest, RetrievalContextResponse


router = APIRouter()


@router.get(
    "/retrieval/search",
    response_model=EvidenceSearchResponse,
    deprecated=True,
    summary="[Deprecated] Use GET /evidence/search",
)
def retrieval_search(
    q: str = Query(..., min_length=2, description="Clinical retrieval query."),
    top_k: int = Query(default=6, ge=1, le=12),
) -> EvidenceSearchResponse:
    return search_evidence(q, top_k)


@router.post("/retrieval/context", response_model=RetrievalContextResponse)
def retrieval_context(payload: RetrievalContextRequest) -> RetrievalContextResponse:
    result = search_evidence(payload.query, payload.top_k)
    return RetrievalContextResponse(
        query=result.query,
        query_terms=result.query_terms,
        graph_facts=result.graph_facts,
        evidence_chunks=result.evidence_chunks,
        context_summary=(
            f"Retrieved {len(result.graph_facts)} graph fact(s) and "
            f"{len(result.evidence_chunks)} evidence chunk(s) for retrieval context."
        ),
        retrieval_sources=result.retrieval_sources,
    )
