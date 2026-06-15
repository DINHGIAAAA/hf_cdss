"""Admin API routes for constraint rule management.

Endpoints:
- GET /constraints - List all constraint rules
- GET /constraints/by-cid/{constraint_id} - List all versions of a rule
- GET /constraints/rules/{rule_id} - Get a specific rule version's details
- POST /constraints/rules/{rule_id}/approve - Approve a draft rule version
- POST /constraints/rules/{rule_id}/retire - Retire an approved rule version
- POST /constraints/rules/{rule_id}/unretire - Restore a retired rule version
- GET /constraints/{constraint_id}/history - Get history for a rule concept
"""
from typing import Any
 
from fastapi import APIRouter, BackgroundTasks, Depends, Header, HTTPException, Query
from pydantic import BaseModel

from app.modules.datastores.postgres import (
    read_constraint_rules_by_status,
    get_constraint_rule,
    approve_constraint_rule,
    retire_constraint_rule,
    unretire_constraint_rule,
    get_constraint_rule_versions,
    rule_with_constraint_id_exists,
    read_constraint_rule_history,
)
from app.modules.constraint_builder.service import invalidate_constraint_cache


router = APIRouter(prefix="/constraints", tags=["admin", "constraints"])


# --- Mock Authentication & Authorization ---
# Trong một ứng dụng thực tế, phần này sẽ được thay thế bằng hệ thống xác thực
# của bạn (ví dụ: OAuth2 with JWT Bearer tokens).

class AdminUser(BaseModel):
    """Mô hình người dùng admin giả lập."""
    id: str
    roles: list[str]

# Cơ sở dữ liệu người dùng giả lập với token tương ứng
MOCK_USERS = {
    "token_clinical_lead": AdminUser(id="dr_lead_1", roles=["admin", "clinical_lead"]),
    "token_admin_only": AdminUser(id="dr_admin_2", roles=["admin"]),
}

async def get_current_admin_user(authorization: str | None = Header(None)) -> AdminUser:
    """Dependency để lấy người dùng từ Authorization header."""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    token = authorization.split(" ")[1]
    user = MOCK_USERS.get(token)
    if not user:
        raise HTTPException(status_code=403, detail="Invalid token or user not found")
    return user

def require_role(required_role: str):
    """Dependency factory để yêu cầu một vai trò cụ thể."""
    async def role_checker(user: AdminUser = Depends(get_current_admin_user)) -> AdminUser:
        if required_role not in user.roles:
            raise HTTPException(status_code=403, detail=f"User does not have the required '{required_role}' role")
        return user
    return role_checker


class ConstraintRuleResponse(BaseModel):
    """Constraint rule response."""
    id: int
    constraint_id: str
    version: int
    target_drug_class: str | None
    action: str
    reason: str
    risk_names: list[str]
    severity_any: list[str]
    evidence_ref: str | None
    clinical_sources: list[dict[str, Any]]
    status: str
    source: str
    approved_by: str | None
    approved_at: str | None
    retired_by: str | None
    retired_at: str | None
    created_at: str
    updated_at: str
    metadata: dict[str, Any]


class ConstraintRuleListResponse(BaseModel):
    """List of constraint rules."""
    total: int
    items: list[ConstraintRuleResponse]
    draft_count: int
    approved_count: int
    retired_count: int


class ConstraintRuleHistoryItem(BaseModel):
    """A single item in the constraint rule's history."""
    history_id: int
    constraint_id: str
    status_from: str | None
    status_to: str
    changed_by: str
    changed_at: str
    reason: str | None

class ConstraintRuleHistoryResponse(BaseModel):
    """Response containing the history of a constraint rule."""
    items: list[ConstraintRuleHistoryItem]


class ConstraintRuleVersionItem(BaseModel):
    """A single version of a constraint rule."""
    id: int
    constraint_id: str
    version: int
    status: str

class ConstraintRuleVersionListResponse(BaseModel):
    """Response containing all versions of a constraint rule."""
    items: list[ConstraintRuleVersionItem]


class RuleActionResponse(BaseModel):
    """Response for actions like approve, retire, unretire."""
    id: int
    constraint_id: str
    status: str
    message: str
    details: dict[str, Any] = {}


@router.get("", response_model=ConstraintRuleListResponse)
def list_constraint_rules(
    status: str | None = Query(None, description="Filter by status: draft, approved, retired"),
    limit: int = Query(100, ge=1, le=500),
) -> ConstraintRuleListResponse:
    """List constraint rules, optionally filtered by status."""
    if status:
        rules = read_constraint_rules_by_status(status, limit=limit)
        items = [ConstraintRuleResponse(**r) for r in rules]
    else:
        # Get all statuses
        draft = read_constraint_rules_by_status("draft", limit=limit)
        approved = read_constraint_rules_by_status("approved", limit=limit)
        retired = read_constraint_rules_by_status("retired", limit=limit)
        rules = draft + approved + retired
        items = [ConstraintRuleResponse(**r) for r in rules]
    
    draft_count = len([r for r in rules if r.get("status") == "draft"])
    approved_count = len([r for r in rules if r.get("status") == "approved"])
    retired_count = len([r for r in rules if r.get("status") == "retired"])
    
    return ConstraintRuleListResponse(
        total=len(rules),
        items=items,
        draft_count=draft_count,
        approved_count=approved_count,
        retired_count=retired_count,
    )


@router.get("/by-cid/{constraint_id}", response_model=ConstraintRuleVersionListResponse)
def get_constraint_rule_versions_endpoint(constraint_id: str) -> ConstraintRuleVersionListResponse:
    """Get all versions of a specific constraint rule by its constraint_id."""
    versions = get_constraint_rule_versions(constraint_id)
    if not versions:
        raise HTTPException(status_code=404, detail="Constraint rule not found")
    return ConstraintRuleVersionListResponse(items=[ConstraintRuleVersionItem(**v) for v in versions])


@router.get("/rules/{rule_id}", response_model=ConstraintRuleResponse)
def get_constraint_rule_endpoint(rule_id: int) -> ConstraintRuleResponse:
    """Get details of a specific constraint rule."""
    rule = get_constraint_rule(rule_id)
    if not rule:
        raise HTTPException(status_code=404, detail="Constraint rule not found")
    return ConstraintRuleResponse(**rule)


@router.post("/rules/{rule_id}/approve", response_model=RuleActionResponse)
def approve_constraint_rule_endpoint(
    rule_id: int,
    background_tasks: BackgroundTasks,
    current_user: AdminUser = Depends(require_role("clinical_lead")),
) -> RuleActionResponse:
    """Approve a draft constraint rule."""
    rule = get_constraint_rule(rule_id)
    if not rule:
        raise HTTPException(status_code=404, detail="Constraint rule not found")
    
    if rule["status"] != "draft":
        raise HTTPException(
            status_code=400,
            detail=f"Can only approve draft rules, this one is {rule['status']}"
        )
    
    success = approve_constraint_rule(rule_id, current_user.id)
    if not success:
        raise HTTPException(status_code=500, detail="Failed to approve constraint rule")
    
    # Invalidate cache so the change is reflected immediately
    background_tasks.add_task(invalidate_constraint_cache)
    
    updated = get_constraint_rule(rule_id)
    return RuleActionResponse(
        id=rule_id,
        constraint_id=updated["constraint_id"],
        status=updated["status"],
        message="Rule approved successfully.",
        details={
            "approved_at": updated["approved_at"],
            "approved_by": updated["approved_by"],
        },
    )


@router.post("/rules/{rule_id}/retire", response_model=RuleActionResponse)
def retire_constraint_rule_endpoint(
    rule_id: int,
    background_tasks: BackgroundTasks,
    current_user: AdminUser = Depends(require_role("admin")),
) -> RuleActionResponse:
    """Retire an approved constraint rule."""
    rule = get_constraint_rule(rule_id)
    if not rule:
        raise HTTPException(status_code=404, detail="Constraint rule not found")
    
    if rule["status"] != "approved":
        raise HTTPException(
            status_code=400,
            detail=f"Can only retire approved rules, this one is {rule['status']}"
        )
    
    success = retire_constraint_rule(rule_id, current_user.id)
    if not success:
        raise HTTPException(status_code=500, detail="Failed to retire constraint rule")
    
    # Invalidate cache so the change is reflected immediately
    background_tasks.add_task(invalidate_constraint_cache)
    
    updated = get_constraint_rule(rule_id)
    return RuleActionResponse(
        id=rule_id,
        constraint_id=updated["constraint_id"],
        status=updated["status"],
        message="Constraint rule retired and no longer used in recommendations.",
        details={
            "retired_at": updated["retired_at"],
            "retired_by": updated["retired_by"],
        },
    )


@router.post("/rules/{rule_id}/unretire", response_model=RuleActionResponse)
def unretire_constraint_rule_endpoint(
    rule_id: int,
    background_tasks: BackgroundTasks,
    current_user: AdminUser = Depends(require_role("admin")),
) -> RuleActionResponse:
    """Un-retire a rule, setting it back to 'approved'."""
    rule = get_constraint_rule(rule_id)
    if not rule:
        raise HTTPException(status_code=404, detail="Constraint rule not found")

    if rule["status"] != "retired":
        raise HTTPException(
            status_code=400,
            detail=f"Can only un-retire retired rules, this one is {rule['status']}"
        )

    success = unretire_constraint_rule(rule_id, current_user.id)
    if not success:
        raise HTTPException(status_code=500, detail="Failed to un-retire constraint rule")

    # Invalidate cache so the change is reflected immediately
    background_tasks.add_task(invalidate_constraint_cache)

    updated = get_constraint_rule(rule_id)
    return RuleActionResponse(
        id=rule_id,
        constraint_id=updated["constraint_id"],
        status=updated["status"],
        message="Constraint rule has been restored to 'approved' status.",
        details={
            "approved_at": updated["approved_at"],
            "approved_by": updated["approved_by"],
        },
    )


@router.get("/{constraint_id}/history", response_model=ConstraintRuleHistoryResponse)
def get_constraint_rule_history_endpoint(
    constraint_id: str,
    current_user: AdminUser = Depends(require_role("admin")),
) -> ConstraintRuleHistoryResponse:
    """Get the status change history of a specific constraint rule."""
    # First, check if any version of the rule exists to provide a proper 404 error
    rule_exists = rule_with_constraint_id_exists(constraint_id)
    if not rule_exists:
        raise HTTPException(status_code=404, detail="Constraint rule not found")
    
    history_items = read_constraint_rule_history(constraint_id)
    return ConstraintRuleHistoryResponse(items=history_items)
