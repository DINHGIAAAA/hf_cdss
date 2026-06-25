from fastapi import APIRouter, Depends, Query

from app.api.routes.admin.deps import require_admin_reader
from app.modules.datastores.postgres import read_audit_events
from app.schemas.common import AuditHistoryResponse


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
