from fastapi import APIRouter, Query

from app.modules.datastores.postgres import read_audit_events


router = APIRouter()


@router.get("/audit/{case_id}")
def case_audit_history(case_id: str, limit: int = Query(default=50, ge=1, le=200)) -> dict:
    events = read_audit_events(case_id, limit)
    return {"case_id": case_id, "events": events}

