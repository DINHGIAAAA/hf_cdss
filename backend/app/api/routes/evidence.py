from fastapi import APIRouter, Query

from app.modules.graphrag.service import search_evidence
from app.schemas.graphrag import EvidenceSearchResponse

router = APIRouter()


@router.get("/evidence/search", response_model=EvidenceSearchResponse)
def evidence_search(
    q: str = Query(..., min_length=2, description="Clinical evidence query."),
    top_k: int = Query(default=6, ge=1, le=12),
) -> EvidenceSearchResponse:
    """Search promoted (published) evidence only — used by clinical runtime and chat."""
    return search_evidence(q, top_k, published=True)
