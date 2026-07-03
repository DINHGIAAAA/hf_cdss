"""Admin API routes for GDMT recommendation policy management."""

from typing import Any, Literal

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from app.api.routes.admin.deps import AdminUser, get_current_admin_user, require_admin_reader, require_catalog_reader, require_role
from app.modules.datastores.gdmt_policies_postgres import (
    approve_gdmt_policy,
    gdmt_policy_with_id_exists,
    get_gdmt_policy,
    get_gdmt_policy_latest_by_status,
    get_gdmt_policy_versions,
    read_gdmt_policies_by_status,
    read_gdmt_policies_filtered,
    read_gdmt_policy_history,
    retire_gdmt_policy,
    unretire_gdmt_policy,
)
from app.modules.gdmt_policy.policy_loader import invalidate_gdmt_policy_cache, load_executable_gdmt_policies
from app.modules.governance.bulk_approve import bulk_approve_gdmt_policies
from app.modules.governance.diff import GDMT_DIFF_FIELDS, diff_field_map, gdmt_diff_payload


router = APIRouter(prefix="/gdmt-policies", tags=["admin", "gdmt-policies"])


class GdmtPolicyResponse(BaseModel):
    id: int
    gdmt_policy_id: str
    version: int
    drug_class_key: str
    display_label: str
    sort_order: int
    policy_body: dict[str, Any]
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


class GdmtPolicyListResponse(BaseModel):
    total: int
    items: list[GdmtPolicyResponse]
    draft_count: int
    approved_count: int
    retired_count: int


class GdmtPolicyStatusUpdate(BaseModel):
    status: Literal["approved", "retired"]


class BulkApproveRequest(BaseModel):
    rule_ids: list[int] | None = None
    drug_class_key: str | None = None
    safety_tier: str | None = None
    q: str | None = None
    limit: int = Field(default=100, ge=1, le=200)


class BulkApproveResponse(BaseModel):
    approved: list[int]
    failed: list[dict[str, Any]]
    skipped: list[int]
    total_requested: int
    message: str


class RuleVersionDiffResponse(BaseModel):
    current: dict[str, Any]
    baseline: dict[str, Any] | None
    changes: list[dict[str, Any]]


class RuleActionResponse(BaseModel):
    id: int
    gdmt_policy_id: str
    status: str
    message: str


def _apply_status_change(rule_id: int, target_status: Literal["approved", "retired"], current_user: AdminUser) -> RuleActionResponse:
    policy = get_gdmt_policy(rule_id)
    if not policy:
        raise HTTPException(status_code=404, detail="GDMT policy not found")

    current_status = policy["status"]
    if target_status == "approved":
        if current_status == "draft":
            require_role(current_user, "clinical_lead")
            if not approve_gdmt_policy(rule_id, current_user.id):
                raise HTTPException(status_code=400, detail="Failed to approve GDMT policy")
        elif current_status == "retired":
            require_role(current_user, "admin")
            if not unretire_gdmt_policy(rule_id, current_user.id):
                raise HTTPException(status_code=400, detail="Failed to un-retire GDMT policy")
        else:
            raise HTTPException(status_code=400, detail=f"Cannot approve GDMT policy in status {current_status}")
    elif target_status == "retired":
        require_role(current_user, "admin")
        if current_status != "approved":
            raise HTTPException(status_code=400, detail="Only approved GDMT policies can be retired")
        if not retire_gdmt_policy(rule_id, current_user.id):
            raise HTTPException(status_code=400, detail="Failed to retire GDMT policy")

    updated = get_gdmt_policy(rule_id)
    return RuleActionResponse(
        id=updated["id"],
        gdmt_policy_id=updated["gdmt_policy_id"],
        status=updated["status"],
        message=f"GDMT policy status updated to {updated['status']}",
    )


@router.get("", response_model=GdmtPolicyListResponse)
def list_gdmt_policies(
    status: str | None = Query(default=None),
    drug_class_key: str | None = Query(default=None),
    safety_tier: str | None = Query(default=None),
    q: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    _: AdminUser = Depends(require_admin_reader),
) -> GdmtPolicyListResponse:
    has_filters = any([drug_class_key, safety_tier, q])
    if has_filters or status:
        items_raw = read_gdmt_policies_filtered(
            status=status,
            drug_class_key=drug_class_key,
            safety_tier=safety_tier,
            q=q,
            limit=limit,
        )
    else:
        draft = read_gdmt_policies_by_status("draft", limit=limit)
        approved = read_gdmt_policies_by_status("approved", limit=limit)
        retired = read_gdmt_policies_by_status("retired", limit=limit)
        items_raw = draft + approved + retired
    return GdmtPolicyListResponse(
        total=len(items_raw),
        items=[GdmtPolicyResponse(**item) for item in items_raw[:limit]],
        draft_count=len([item for item in items_raw if item["status"] == "draft"]),
        approved_count=len([item for item in items_raw if item["status"] == "approved"]),
        retired_count=len([item for item in items_raw if item["status"] == "retired"]),
    )


@router.post("/bulk-approve", response_model=BulkApproveResponse)
def bulk_approve_gdmt_policies_endpoint(
    payload: BulkApproveRequest,
    background_tasks: BackgroundTasks,
    current_user: AdminUser = Depends(get_current_admin_user),
) -> BulkApproveResponse:
    require_role(current_user, "clinical_lead")
    result = bulk_approve_gdmt_policies(
        current_user.id,
        rule_ids=payload.rule_ids,
        drug_class_key=payload.drug_class_key,
        safety_tier=payload.safety_tier,
        q=payload.q,
        limit=payload.limit,
    )
    background_tasks.add_task(invalidate_gdmt_policy_cache)
    return BulkApproveResponse(**result)


@router.get("/active")
def list_active_gdmt_policies(_: AdminUser = Depends(require_catalog_reader)) -> list[dict[str, Any]]:
    return load_executable_gdmt_policies()


@router.get("/rules/{rule_id}", response_model=GdmtPolicyResponse)
def get_gdmt_policy_endpoint(rule_id: int, _: AdminUser = Depends(require_admin_reader)) -> GdmtPolicyResponse:
    policy = get_gdmt_policy(rule_id)
    if not policy:
        raise HTTPException(status_code=404, detail="GDMT policy not found")
    return GdmtPolicyResponse(**policy)


def _resolve_gdmt_baseline(policy: dict[str, Any], against: str) -> dict[str, Any] | None:
    if against == "approved":
        baseline = get_gdmt_policy_latest_by_status(policy["gdmt_policy_id"], "approved")
        if baseline and baseline["id"] == policy["id"]:
            return None
        return baseline
    if against == "previous":
        versions = get_gdmt_policy_versions(policy["gdmt_policy_id"])
        previous = next((item for item in versions if item["version"] == policy["version"] - 1), None)
        return get_gdmt_policy(previous["id"]) if previous else None
    try:
        baseline_id = int(against)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="against must be approved, previous, or a rule id") from exc
    baseline = get_gdmt_policy(baseline_id)
    if not baseline or baseline["gdmt_policy_id"] != policy["gdmt_policy_id"]:
        raise HTTPException(status_code=404, detail="Baseline policy version not found")
    return baseline


@router.get("/rules/{rule_id}/diff", response_model=RuleVersionDiffResponse)
def get_gdmt_policy_diff_endpoint(
    rule_id: int,
    against: str = Query("approved", description="approved | previous | {rule_id}"),
    _: AdminUser = Depends(require_admin_reader),
) -> RuleVersionDiffResponse:
    current = get_gdmt_policy(rule_id)
    if not current:
        raise HTTPException(status_code=404, detail="GDMT policy not found")
    baseline = _resolve_gdmt_baseline(current, against)
    changes = diff_field_map(
        gdmt_diff_payload(baseline or {}),
        gdmt_diff_payload(current),
        GDMT_DIFF_FIELDS,
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
def update_gdmt_policy_status(
    rule_id: int,
    payload: GdmtPolicyStatusUpdate,
    background_tasks: BackgroundTasks,
    current_user: AdminUser = Depends(get_current_admin_user),
) -> RuleActionResponse:
    response = _apply_status_change(rule_id, payload.status, current_user)
    background_tasks.add_task(invalidate_gdmt_policy_cache)
    return response


@router.get("/by-rid/{gdmt_policy_id}")
def get_gdmt_policy_versions_endpoint(
    gdmt_policy_id: str,
    _: AdminUser = Depends(require_admin_reader),
) -> dict[str, Any]:
    return {"items": get_gdmt_policy_versions(gdmt_policy_id)}


@router.get("/{gdmt_policy_id}/history")
def get_gdmt_policy_history_endpoint(
    gdmt_policy_id: str,
    _: AdminUser = Depends(require_admin_reader),
) -> dict[str, Any]:
    if not gdmt_policy_with_id_exists(gdmt_policy_id):
        raise HTTPException(status_code=404, detail="GDMT policy not found")
    return {"items": read_gdmt_policy_history(gdmt_policy_id)}
