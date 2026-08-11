from fastapi import APIRouter, Depends, Query

from app.api.routes.admin.deps import require_admin_reader
from app.modules.datastores.postgres import read_audit_events, search_chat_audit_events
from app.schemas.common import AuditHistoryResponse, ChatAuditLogResponse


router = APIRouter(prefix="/audit", tags=["admin", "audit"])


@router.get("/cases/{case_id}", response_model=AuditHistoryResponse)
def admin_case_audit_history(
    case_id: str,
    limit: int = Query(default=50, ge=1, le=200),
    _current_user=Depends(require_admin_reader),
) -> AuditHistoryResponse:
    try:
        events = read_audit_events(case_id, limit)
        return AuditHistoryResponse(case_id=case_id, events=events)
    except Exception as exc:
        return AuditHistoryResponse(
            case_id=case_id,
            events=[],
            status=f"unavailable: {exc}",
        )


@router.get("/chat", response_model=ChatAuditLogResponse)
def admin_chat_audit_log(
    q: str | None = Query(default=None, description="Search question, answer, or intent"),
    case_id: str | None = Query(default=None, description="Filter by case / conversation id"),
    limit: int = Query(default=30, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    _current_user=Depends(require_admin_reader),
) -> ChatAuditLogResponse:
    try:
        result = search_chat_audit_events(q=q, case_id=case_id, limit=limit, offset=offset)
        return ChatAuditLogResponse(**result)
    except Exception as exc:
        return ChatAuditLogResponse(
            total=0,
            limit=limit,
            offset=offset,
            items=[],
            status=f"unavailable: {exc}",
        )
