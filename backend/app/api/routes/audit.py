from fastapi import APIRouter, Query

from app.modules.datastores.postgres import read_audit_events
from app.schemas.common import AuditHistoryResponse


router = APIRouter()


@router.get("/audit/{case_id}", response_model=AuditHistoryResponse)
def case_audit_history(case_id: str, limit: int = Query(default=50, ge=1, le=200)) -> AuditHistoryResponse:
    try:
        events = read_audit_events(case_id, limit)
        return AuditHistoryResponse(case_id=case_id, events=events)
    except Exception as exc:
        return AuditHistoryResponse(
            case_id=case_id,
            events=[],
            status=f"unavailable: {exc}",
        )
