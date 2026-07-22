"""Admin API routes for interaction rule management."""

from typing import Any, Literal

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from app.api.routes.admin.deps import AdminUser, ensure_role, get_current_admin_user, require_admin_reader, require_catalog_reader, require_role
from app.modules.datastores.interaction_rules_postgres import (
    approve_interaction_rule,
    count_interaction_rules_by_status,
    get_interaction_rule,
    get_interaction_rule_latest_by_status,
    get_interaction_rule_versions,
    interaction_rule_with_id_exists,
    read_interaction_rule_history,
    read_interaction_rules_by_status,
    read_interaction_rules_filtered,
    retire_interaction_rule,
    unretire_interaction_rule,
)
from app.modules.governance.bulk_approve import bulk_approve_interaction_rules
from app.modules.governance.diff import INTERACTION_DIFF_FIELDS, diff_field_map, interaction_diff_payload
from app.modules.interaction_checking.rule_loader import invalidate_interaction_rules_cache, load_executable_interaction_rules


router = APIRouter(prefix="/interaction-rules", tags=["admin", "interaction-rules"])


class InteractionRuleResponse(BaseModel):
    id: int
    interaction_rule_id: str
    version: int
    drug_set_a: list[str]
    drug_set_b: list[str]
    severity: str
    target: str | None
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


class InteractionRuleListResponse(BaseModel):
    total: int
    items: list[InteractionRuleResponse]
    draft_count: int
    approved_count: int
    retired_count: int


class InteractionRuleStatusUpdate(BaseModel):
    status: Literal["approved", "retired"]


class BulkApproveRequest(BaseModel):
    rule_ids: list[int] | None = None
    severity: str | None = None
    target: str | None = None
    safety_tier: str | None = None
    q: str | None = None
    extraction_method: str | None = None
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
    interaction_rule_id: str
    status: str
    message: str


def _apply_status_change(rule_id: int, target_status: Literal["approved", "retired"], current_user: AdminUser) -> RuleActionResponse:
    rule = get_interaction_rule(rule_id)
    if not rule:
        raise HTTPException(status_code=404, detail="Interaction rule not found")

    current_status = rule["status"]
    if target_status == "approved":
        if current_status == "draft":
            ensure_role(current_user, "clinical_lead")
            if not approve_interaction_rule(rule_id, current_user.id):
                raise HTTPException(status_code=400, detail="Failed to approve interaction rule")
        elif current_status == "retired":
            ensure_role(current_user, "admin")
            if not unretire_interaction_rule(rule_id, current_user.id):
                raise HTTPException(status_code=400, detail="Failed to un-retire interaction rule")
        else:
            raise HTTPException(status_code=400, detail=f"Cannot approve interaction rule in status {current_status}")
    elif target_status == "retired":
        ensure_role(current_user, "admin")
        if current_status != "approved":
            raise HTTPException(status_code=400, detail="Only approved interaction rules can be retired")
        if not retire_interaction_rule(rule_id, current_user.id):
            raise HTTPException(status_code=400, detail="Failed to retire interaction rule")

    updated = get_interaction_rule(rule_id)
    return RuleActionResponse(
        id=updated["id"],
        interaction_rule_id=updated["interaction_rule_id"],
        status=updated["status"],
        message=f"Interaction rule status updated to {updated['status']}",
    )


@router.get("", response_model=InteractionRuleListResponse)
def list_interaction_rules(
    status: str | None = Query(default=None),
    severity: str | None = Query(default=None),
    target: str | None = Query(default=None),
    safety_tier: str | None = Query(default=None),
    q: str | None = Query(default=None),
    extraction_method: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    _: AdminUser = Depends(require_admin_reader),
) -> InteractionRuleListResponse:
    has_filters = any([severity, target, safety_tier, q, extraction_method])
    if has_filters or status:
        items_raw = read_interaction_rules_filtered(
            status=status,
            severity=severity,
            target=target,
            safety_tier=safety_tier,
            q=q,
            extraction_method=extraction_method,
            limit=limit,
        )
    else:
        draft = read_interaction_rules_by_status("draft", limit=limit)
        approved = read_interaction_rules_by_status("approved", limit=limit)
        retired = read_interaction_rules_by_status("retired", limit=limit)
        items_raw = draft + approved + retired
    counts = count_interaction_rules_by_status(
        severity=severity,
        target=target,
        safety_tier=safety_tier,
        q=q,
        extraction_method=extraction_method,
    )
    return InteractionRuleListResponse(
        total=len(items_raw),
        items=[InteractionRuleResponse(**item) for item in items_raw[:limit]],
        draft_count=counts["draft"],
        approved_count=counts["approved"],
        retired_count=counts["retired"],
    )


@router.post("/bulk-approve", response_model=BulkApproveResponse)
def bulk_approve_interaction_rules_endpoint(
    payload: BulkApproveRequest,
    background_tasks: BackgroundTasks,
    current_user: AdminUser = Depends(require_role("clinical_lead")),
) -> BulkApproveResponse:
    result = bulk_approve_interaction_rules(
        current_user.id,
        rule_ids=payload.rule_ids,
        severity=payload.severity,
        target=payload.target,
        safety_tier=payload.safety_tier,
        q=payload.q,
        extraction_method=payload.extraction_method,
        limit=payload.limit,
        dry_run=payload.dry_run,
    )
    if not payload.dry_run:
        background_tasks.add_task(invalidate_interaction_rules_cache)
    return BulkApproveResponse(**result)


@router.get("/active")
def list_active_interaction_rules(_: AdminUser = Depends(require_catalog_reader)) -> list[dict[str, Any]]:
    return load_executable_interaction_rules()


@router.get("/rules/{rule_id}", response_model=InteractionRuleResponse)
def get_interaction_rule_endpoint(rule_id: int, _: AdminUser = Depends(require_admin_reader)) -> InteractionRuleResponse:
    rule = get_interaction_rule(rule_id)
    if not rule:
        raise HTTPException(status_code=404, detail="Interaction rule not found")
    return InteractionRuleResponse(**rule)


def _resolve_interaction_baseline(rule: dict[str, Any], against: str) -> dict[str, Any] | None:
    if against == "approved":
        baseline = get_interaction_rule_latest_by_status(rule["interaction_rule_id"], "approved")
        if baseline and baseline["id"] == rule["id"]:
            return None
        return baseline
    if against == "previous":
        versions = get_interaction_rule_versions(rule["interaction_rule_id"])
        previous = next((item for item in versions if item["version"] == rule["version"] - 1), None)
        return get_interaction_rule(previous["id"]) if previous else None
    try:
        baseline_id = int(against)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="against must be approved, previous, or a rule id") from exc
    baseline = get_interaction_rule(baseline_id)
    if not baseline or baseline["interaction_rule_id"] != rule["interaction_rule_id"]:
        raise HTTPException(status_code=404, detail="Baseline rule version not found")
    return baseline


@router.get("/rules/{rule_id}/diff", response_model=RuleVersionDiffResponse)
def get_interaction_rule_diff_endpoint(
    rule_id: int,
    against: str = Query("approved", description="approved | previous | {rule_id}"),
    _: AdminUser = Depends(require_admin_reader),
) -> RuleVersionDiffResponse:
    current = get_interaction_rule(rule_id)
    if not current:
        raise HTTPException(status_code=404, detail="Interaction rule not found")
    baseline = _resolve_interaction_baseline(current, against)
    changes = diff_field_map(
        interaction_diff_payload(baseline or {}),
        interaction_diff_payload(current),
        INTERACTION_DIFF_FIELDS,
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
def update_interaction_rule_status(
    rule_id: int,
    payload: InteractionRuleStatusUpdate,
    background_tasks: BackgroundTasks,
    current_user: AdminUser = Depends(get_current_admin_user),
) -> RuleActionResponse:
    response = _apply_status_change(rule_id, payload.status, current_user)
    background_tasks.add_task(invalidate_interaction_rules_cache)
    return response


@router.get("/by-rid/{interaction_rule_id}")
def get_interaction_rule_versions_endpoint(
    interaction_rule_id: str,
    _: AdminUser = Depends(require_admin_reader),
) -> dict[str, Any]:
    return {"items": get_interaction_rule_versions(interaction_rule_id)}


@router.get("/{interaction_rule_id}/history")
def get_interaction_rule_history_endpoint(
    interaction_rule_id: str,
    _: AdminUser = Depends(require_admin_reader),
) -> dict[str, Any]:
    if not interaction_rule_with_id_exists(interaction_rule_id):
        raise HTTPException(status_code=404, detail="Interaction rule not found")
    return {"items": read_interaction_rule_history(interaction_rule_id)}
