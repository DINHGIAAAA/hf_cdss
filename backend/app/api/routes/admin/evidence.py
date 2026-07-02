from fastapi import APIRouter, Depends, Query

from app.api.routes.admin.deps import AdminUser, require_admin_reader
from app.modules.graphrag.service import search_evidence
from app.schemas.graphrag import EvidenceSearchResponse

router = APIRouter()


@router.get("/evidence/search", response_model=EvidenceSearchResponse)
def admin_evidence_search(
    q: str = Query(..., min_length=2, description="Clinical evidence query."),
    top_k: int = Query(default=10, ge=1, le=12),
    staging: bool = Query(
        default=True,
        description="When true, search workspace (draft) artifacts. When false, search promoted current index.",
    ),
    _current_user: AdminUser = Depends(require_admin_reader),
) -> EvidenceSearchResponse:
    """Admin-only evidence search across draft workspace or promoted artifacts."""
    return search_evidence(q, top_k, published=not staging)
