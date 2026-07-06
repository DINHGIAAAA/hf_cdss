"""Admin API routes for dose rule management."""

from typing import Any, Literal

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from app.api.routes.admin.deps import AdminUser, get_current_admin_user, require_admin_reader, require_catalog_reader, require_role
from app.modules.datastores.postgres import (
    approve_dose_rule,
    dose_rule_with_id_exists,
    get_dose_rule,
    get_dose_rule_latest_by_status,
    get_dose_rule_versions,
    read_dose_rule_history,
    read_dose_rules_by_status,
    read_dose_rules_filtered,
    retire_dose_rule,
    unretire_dose_rule,
)
from app.modules.dose_calculator.registry import invalidate_dose_rules_registry_cache, load_dose_rules
from app.modules.governance.bulk_approve import bulk_approve_dose_rules
from app.modules.governance.diff import DOSE_DIFF_FIELDS, diff_field_map, dose_diff_payload


router = APIRouter(prefix="/dose-rules", tags=["admin", "dose-rules"])


class DoseRuleResponse(BaseModel):
    id: int
    dose_rule_id: str
    version: int
    drug_keys: list[str]
    drug_class: str | None
    calculation_type: str
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


class DoseRuleListResponse(BaseModel):
    total: int
    items: list[DoseRuleResponse]
    draft_count: int
    approved_count: int
    retired_count: int


class DoseRuleStatusUpdate(BaseModel):
    status: Literal["approved", "retired"]


class BulkApproveRequest(BaseModel):
    rule_ids: list[int] | None = None
    drug_class: str | None = None
    calculation_type: str | None = None
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
    dose_rule_id: str
    status: str
    message: str


def _apply_status_change(rule_id: int, target_status: Literal["approved", "retired"], current_user: AdminUser) -> RuleActionResponse:
    rule = get_dose_rule(rule_id)
    if not rule:
        raise HTTPException(status_code=404, detail="Dose rule not found")

    current_status = rule["status"]
    if target_status == "approved":
        if current_status == "draft":
            require_role(current_user, "clinical_lead")
            if not approve_dose_rule(rule_id, current_user.id):
                raise HTTPException(status_code=400, detail="Failed to approve dose rule")
        elif current_status == "retired":
            require_role(current_user, "admin")
            if not unretire_dose_rule(rule_id, current_user.id):
                raise HTTPException(status_code=400, detail="Failed to un-retire dose rule")
        else:
            raise HTTPException(status_code=400, detail=f"Cannot approve dose rule in status {current_status}")
    elif target_status == "retired":
        require_role(current_user, "admin")
        if current_status != "approved":
            raise HTTPException(status_code=400, detail="Only approved dose rules can be retired")
        if not retire_dose_rule(rule_id, current_user.id):
            raise HTTPException(status_code=400, detail="Failed to retire dose rule")

    updated = get_dose_rule(rule_id)
    return RuleActionResponse(
        id=updated["id"],
        dose_rule_id=updated["dose_rule_id"],
        status=updated["status"],
        message=f"Dose rule status updated to {updated['status']}",
    )


@router.get("", response_model=DoseRuleListResponse)
def list_dose_rules(
    status: str | None = Query(default=None),
    drug_class: str | None = Query(default=None),
    calculation_type: str | None = Query(default=None),
    safety_tier: str | None = Query(default=None),
    q: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    _: AdminUser = Depends(require_admin_reader),
) -> DoseRuleListResponse:
    has_filters = any([drug_class, calculation_type, safety_tier, q])
    if has_filters or status:
        items_raw = read_dose_rules_filtered(
            status=status,
            drug_class=drug_class,
            calculation_type=calculation_type,
            safety_tier=safety_tier,
            q=q,
            limit=limit,
        )
    else:
        draft = read_dose_rules_by_status("draft", limit=limit)
        approved = read_dose_rules_by_status("approved", limit=limit)
        retired = read_dose_rules_by_status("retired", limit=limit)
        items_raw = draft + approved + retired
    return DoseRuleListResponse(
        total=len(items_raw),
        items=[DoseRuleResponse(**item) for item in items_raw[:limit]],
        draft_count=len([item for item in items_raw if item["status"] == "draft"]),
        approved_count=len([item for item in items_raw if item["status"] == "approved"]),
        retired_count=len([item for item in items_raw if item["status"] == "retired"]),
    )


@router.post("/bulk-approve", response_model=BulkApproveResponse)
def bulk_approve_dose_rules_endpoint(
    payload: BulkApproveRequest,
    background_tasks: BackgroundTasks,
    current_user: AdminUser = Depends(get_current_admin_user),
) -> BulkApproveResponse:
    require_role(current_user, "clinical_lead")
    result = bulk_approve_dose_rules(
        current_user.id,
        rule_ids=payload.rule_ids,
        drug_class=payload.drug_class,
        calculation_type=payload.calculation_type,
        safety_tier=payload.safety_tier,
        q=payload.q,
        limit=payload.limit,
        dry_run=payload.dry_run,
    )
    if not payload.dry_run:
        background_tasks.add_task(invalidate_dose_rules_registry_cache)
    return BulkApproveResponse(**result)


@router.get("/active")
def list_active_dose_rules(_: AdminUser = Depends(require_catalog_reader)) -> list[dict[str, Any]]:
    return load_dose_rules()


@router.get("/rules/{rule_id}", response_model=DoseRuleResponse)
def get_dose_rule_endpoint(rule_id: int, _: AdminUser = Depends(require_admin_reader)) -> DoseRuleResponse:
    rule = get_dose_rule(rule_id)
    if not rule:
        raise HTTPException(status_code=404, detail="Dose rule not found")
    return DoseRuleResponse(**rule)


def _resolve_dose_baseline(rule: dict[str, Any], against: str) -> dict[str, Any] | None:
    if against == "approved":
        baseline = get_dose_rule_latest_by_status(rule["dose_rule_id"], "approved")
        if baseline and baseline["id"] == rule["id"]:
            return None
        return baseline
    if against == "previous":
        versions = get_dose_rule_versions(rule["dose_rule_id"])
        previous = next((item for item in versions if item["version"] == rule["version"] - 1), None)
        return get_dose_rule(previous["id"]) if previous else None
    try:
        baseline_id = int(against)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="against must be approved, previous, or a rule id") from exc
    baseline = get_dose_rule(baseline_id)
    if not baseline or baseline["dose_rule_id"] != rule["dose_rule_id"]:
        raise HTTPException(status_code=404, detail="Baseline rule version not found")
    return baseline


@router.get("/rules/{rule_id}/diff", response_model=RuleVersionDiffResponse)
def get_dose_rule_diff_endpoint(
    rule_id: int,
    against: str = Query("approved", description="approved | previous | {rule_id}"),
    _: AdminUser = Depends(require_admin_reader),
) -> RuleVersionDiffResponse:
    current = get_dose_rule(rule_id)
    if not current:
        raise HTTPException(status_code=404, detail="Dose rule not found")
    baseline = _resolve_dose_baseline(current, against)
    changes = diff_field_map(
        dose_diff_payload(baseline or {}),
        dose_diff_payload(current),
        DOSE_DIFF_FIELDS,
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
def update_dose_rule_status(
    rule_id: int,
    payload: DoseRuleStatusUpdate,
    background_tasks: BackgroundTasks,
    current_user: AdminUser = Depends(get_current_admin_user),
) -> RuleActionResponse:
    response = _apply_status_change(rule_id, payload.status, current_user)
    background_tasks.add_task(invalidate_dose_rules_registry_cache)
    return response


@router.get("/by-rid/{dose_rule_id}")
def get_dose_rule_versions_endpoint(dose_rule_id: str, _: AdminUser = Depends(require_admin_reader)) -> dict[str, Any]:
    return {"items": get_dose_rule_versions(dose_rule_id)}


@router.get("/{dose_rule_id}/history")
def get_dose_rule_history_endpoint(dose_rule_id: str, _: AdminUser = Depends(require_admin_reader)) -> dict[str, Any]:
    if not dose_rule_with_id_exists(dose_rule_id):
        raise HTTPException(status_code=404, detail="Dose rule not found")
    return {"items": read_dose_rule_history(dose_rule_id)}
