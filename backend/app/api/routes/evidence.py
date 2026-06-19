from typing import Any

from fastapi import APIRouter, Query

from app.modules.constraint_builder.service import load_constraint_rules
from app.modules.graphrag.service import search_evidence
from app.schemas.graphrag import EvidenceSearchResponse


router = APIRouter()


@router.get("/constraint-rules/active")
def active_constraint_rules() -> list[dict[str, Any]]:
    """Active constraint rules loaded by the CDSS runtime."""
    return load_constraint_rules()


@router.get("/rules", deprecated=True, summary="[Deprecated] Use GET /constraint-rules/active")
def rules_legacy() -> list[dict[str, Any]]:
    return active_constraint_rules()


@router.get("/evidence/search", response_model=EvidenceSearchResponse)
def evidence_search(
    q: str = Query(..., min_length=2, description="Clinical evidence query."),
    top_k: int = Query(default=6, ge=1, le=12),
) -> EvidenceSearchResponse:
    return search_evidence(q, top_k)
