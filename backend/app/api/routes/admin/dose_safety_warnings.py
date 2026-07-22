"""Admin API routes for dose safety warning management."""

from typing import Any, Literal

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from app.api.routes.admin.deps import AdminUser, ensure_role, get_current_admin_user, require_admin_reader, require_catalog_reader, require_role
from app.modules.datastores.dose_safety_warnings_postgres import (
    approve_dose_safety_warning,
    count_dose_safety_warnings_by_status,
    dose_safety_warning_with_id_exists,
    get_dose_safety_warning,
    get_dose_safety_warning_latest_by_status,
    get_dose_safety_warning_versions,
    read_dose_safety_warning_history,
    read_dose_safety_warnings_by_status,
    read_dose_safety_warnings_filtered,
    retire_dose_safety_warning,
    unretire_dose_safety_warning,
)
from app.modules.dose_safety.rule_loader import invalidate_dose_safety_warnings_cache, load_executable_dose_safety_warnings
from app.modules.governance.bulk_approve import bulk_approve_dose_safety_warnings
from app.modules.governance.diff import DOSE_SAFETY_DIFF_FIELDS, diff_field_map, dose_safety_diff_payload


router = APIRouter(prefix="/dose-safety-warnings", tags=["admin", "dose-safety-warnings"])


class DoseSafetyWarningResponse(BaseModel):
    id: int
    dose_safety_warning_id: str
    version: int
    drug_keys: list[str]
    target: str | None
    default_severity: str
    rule_body: dict[str, Any]
    evidence_ref: str | None
    clinical_sources: list[dict[str, Any]]
    status: str
    source: str
    safety_tier: str | None = None
    approved_by: str | None = None
    approved_at: str | None = None
    retired_by: str | None = None
    retired_at: str | None = None
    created_at: str
    updated_at: str
    metadata: dict[str, Any]


class DoseSafetyWarningListResponse(BaseModel):
    total: int
    items: list[DoseSafetyWarningResponse]
    draft_count: int
    approved_count: int
    retired_count: int


class DoseSafetyWarningStatusUpdate(BaseModel):
    status: Literal["approved", "retired"]


class BulkApproveRequest(BaseModel):
    rule_ids: list[int] | None = None
    target: str | None = None
    default_severity: str | None = None
    safety_tier: str | None = None
    q: str | None = None
    limit: int = Field(default=100, ge=1, le=200)
    dry_run: bool = Field(default=False, description="Preview candidate ids without approving")


class BulkApproveResponse(BaseModel):
    approved: list[int]
    failed: list[dict[str, Any]]
    skipped: list[int]
    total_requested: int
    message: str
    dry_run: bool = False
    candidate_ids: list[int] = Field(default_factory=list)


class RuleVersionDiffResponse(BaseModel):
    current: dict[str, Any]
    baseline: dict[str, Any] | None
    changes: list[dict[str, Any]]


class RuleActionResponse(BaseModel):
    id: int
    dose_safety_warning_id: str
    status: str
    message: str


def _apply_status_change(rule_id: int, target_status: Literal["approved", "retired"], current_user: AdminUser) -> RuleActionResponse:
    warning = get_dose_safety_warning(rule_id)
    if not warning:
        raise HTTPException(status_code=404, detail="Dose safety warning not found")

    current_status = warning["status"]
    if target_status == "approved":
        if current_status == "draft":
            ensure_role(current_user, "clinical_lead")
            if not approve_dose_safety_warning(rule_id, current_user.id):
                raise HTTPException(status_code=400, detail="Failed to approve dose safety warning")
        elif current_status == "retired":
            ensure_role(current_user, "admin")
            if not unretire_dose_safety_warning(rule_id, current_user.id):
                raise HTTPException(status_code=400, detail="Failed to un-retire dose safety warning")
        else:
            raise HTTPException(status_code=400, detail=f"Cannot approve dose safety warning in status {current_status}")
    elif target_status == "retired":
        ensure_role(current_user, "admin")
        if current_status != "approved":
            raise HTTPException(status_code=400, detail="Only approved dose safety warnings can be retired")
        if not retire_dose_safety_warning(rule_id, current_user.id):
            raise HTTPException(status_code=400, detail="Failed to retire dose safety warning")

    updated = get_dose_safety_warning(rule_id)
    return RuleActionResponse(
        id=updated["id"],
        dose_safety_warning_id=updated["dose_safety_warning_id"],
        status=updated["status"],
        message=f"Dose safety warning status updated to {updated['status']}",
    )


@router.get("", response_model=DoseSafetyWarningListResponse)
def list_dose_safety_warnings(
    status: str | None = Query(default=None),
    target: str | None = Query(default=None),
    default_severity: str | None = Query(default=None),
    safety_tier: str | None = Query(default=None),
    q: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    _: AdminUser = Depends(require_admin_reader),
) -> DoseSafetyWarningListResponse:
    has_filters = any([target, default_severity, safety_tier, q])
    if has_filters or status:
        items_raw = read_dose_safety_warnings_filtered(
            status=status,
            target=target,
            default_severity=default_severity,
            safety_tier=safety_tier,
            q=q,
            limit=limit,
        )
    else:
        draft = read_dose_safety_warnings_by_status("draft", limit=limit)
        approved = read_dose_safety_warnings_by_status("approved", limit=limit)
        retired = read_dose_safety_warnings_by_status("retired", limit=limit)
        items_raw = draft + approved + retired
    counts = count_dose_safety_warnings_by_status(
        target=target,
        default_severity=default_severity,
        safety_tier=safety_tier,
        q=q,
    )
    return DoseSafetyWarningListResponse(
        total=len(items_raw),
        items=[DoseSafetyWarningResponse(**item) for item in items_raw[:limit]],
        draft_count=counts["draft"],
        approved_count=counts["approved"],
        retired_count=counts["retired"],
    )


@router.post("/bulk-approve", response_model=BulkApproveResponse)
def bulk_approve_dose_safety_warnings_endpoint(
    payload: BulkApproveRequest,
    background_tasks: BackgroundTasks,
    current_user: AdminUser = Depends(require_role("clinical_lead")),
) -> BulkApproveResponse:
    result = bulk_approve_dose_safety_warnings(
        current_user.id,
        rule_ids=payload.rule_ids,
        target=payload.target,
        default_severity=payload.default_severity,
        safety_tier=payload.safety_tier,
        q=payload.q,
        limit=payload.limit,
        dry_run=payload.dry_run,
    )
    if not payload.dry_run:
        background_tasks.add_task(invalidate_dose_safety_warnings_cache)
    return BulkApproveResponse(**result)


@router.get("/active")
def list_active_dose_safety_warnings(_: AdminUser = Depends(require_catalog_reader)) -> list[dict[str, Any]]:
    return load_executable_dose_safety_warnings()


@router.get("/rules/{rule_id}", response_model=DoseSafetyWarningResponse)
def get_dose_safety_warning_endpoint(rule_id: int, _: AdminUser = Depends(require_admin_reader)) -> DoseSafetyWarningResponse:
    warning = get_dose_safety_warning(rule_id)
    if not warning:
        raise HTTPException(status_code=404, detail="Dose safety warning not found")
    return DoseSafetyWarningResponse(**warning)


def _resolve_baseline(warning: dict[str, Any], against: str) -> dict[str, Any] | None:
    if against == "approved":
        baseline = get_dose_safety_warning_latest_by_status(warning["dose_safety_warning_id"], "approved")
        if baseline and baseline["id"] == warning["id"]:
            return None
        return baseline
    if against == "previous":
        versions = get_dose_safety_warning_versions(warning["dose_safety_warning_id"])
        previous = next((item for item in versions if item["version"] == warning["version"] - 1), None)
        return get_dose_safety_warning(previous["id"]) if previous else None
    try:
        baseline_id = int(against)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="against must be approved, previous, or a rule id") from exc
    baseline = get_dose_safety_warning(baseline_id)
    if not baseline or baseline["dose_safety_warning_id"] != warning["dose_safety_warning_id"]:
        raise HTTPException(status_code=404, detail="Baseline warning version not found")
    return baseline


@router.get("/rules/{rule_id}/diff", response_model=RuleVersionDiffResponse)
def get_dose_safety_warning_diff_endpoint(
    rule_id: int,
    against: str = Query("approved", description="approved | previous | {rule_id}"),
    _: AdminUser = Depends(require_admin_reader),
) -> RuleVersionDiffResponse:
    current = get_dose_safety_warning(rule_id)
    if not current:
        raise HTTPException(status_code=404, detail="Dose safety warning not found")
    baseline = _resolve_baseline(current, against)
    changes = diff_field_map(
        dose_safety_diff_payload(baseline or {}),
        dose_safety_diff_payload(current),
        DOSE_SAFETY_DIFF_FIELDS,
    )
    return RuleVersionDiffResponse(
        current={"id": current["id"], "version": current["version"], "status": current["status"]},
        baseline=(
            {"id": baseline["id"], "version": baseline["version"], "status": baseline["status"]}
            if baseline
            else None
        ),
        changes=changes,
    )


@router.patch("/rules/{rule_id}", response_model=RuleActionResponse)
def update_dose_safety_warning_status(
    rule_id: int,
    payload: DoseSafetyWarningStatusUpdate,
    background_tasks: BackgroundTasks,
    current_user: AdminUser = Depends(get_current_admin_user),
) -> RuleActionResponse:
    response = _apply_status_change(rule_id, payload.status, current_user)
    background_tasks.add_task(invalidate_dose_safety_warnings_cache)
    return response


@router.get("/by-rid/{dose_safety_warning_id}")
def get_dose_safety_warning_versions_endpoint(
    dose_safety_warning_id: str,
    _: AdminUser = Depends(require_admin_reader),
) -> dict[str, Any]:
    return {"items": get_dose_safety_warning_versions(dose_safety_warning_id)}


@router.get("/{dose_safety_warning_id}/history")
def get_dose_safety_warning_history_endpoint(
    dose_safety_warning_id: str,
    _: AdminUser = Depends(require_admin_reader),
) -> dict[str, Any]:
    if not dose_safety_warning_with_id_exists(dose_safety_warning_id):
        raise HTTPException(status_code=404, detail="Dose safety warning not found")
    return {"items": read_dose_safety_warning_history(dose_safety_warning_id)}
