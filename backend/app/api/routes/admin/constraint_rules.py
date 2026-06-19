"""Admin API routes for constraint rule management.

Endpoints:
- GET /constraints - List all constraint rules
- GET /constraints/by-cid/{constraint_id} - List all versions of a rule
- GET /constraints/rules/{rule_id} - Get a specific rule version's details
- PATCH /constraints/rules/{rule_id} - Update rule status (approved, retired)
- POST /constraints/rules/{rule_id}/approve - [Deprecated] Use PATCH with status=approved
- POST /constraints/rules/{rule_id}/retire - [Deprecated] Use PATCH with status=retired
- POST /constraints/rules/{rule_id}/unretire - [Deprecated] Use PATCH with status=approved
- GET /constraints/{constraint_id}/history - Get history for a rule concept
"""
from typing import Any, Literal
 
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from app.core.jwt import JWTError, jwt
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
from app.core.config import settings
from app.api.routes.auth import redis_client, oauth2_scheme


router = APIRouter(prefix="/constraints", tags=["admin", "constraints"])


class AdminUser(BaseModel):
    """Mô hình thông tin người dùng admin từ JWT Token."""
    id: str
    roles: list[str]

async def get_current_admin_user(token: str = Depends(oauth2_scheme)) -> AdminUser:
    """Dependency xác thực và giải mã JWT token."""
    credentials_exception = HTTPException(
        status_code=401,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    
    is_blocked = await redis_client.get(f"blocklist:{token}")
    if is_blocked:
        raise HTTPException(status_code=401, detail="Token has been revoked (Logged out)")
        
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret_key,
            algorithms=[settings.jwt_algorithm],
        )
        user_id: str | None = payload.get("sub")
        roles: list[str] = payload.get("roles", [])
        
        if user_id is None:
            raise credentials_exception
        return AdminUser(id=user_id, roles=roles)
    except JWTError:
        raise credentials_exception

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
    """Response for status updates and legacy action endpoints."""
    id: int
    constraint_id: str
    status: str
    message: str
    details: dict[str, Any] = {}


class ConstraintRuleStatusUpdate(BaseModel):
    """Request body for PATCH /rules/{rule_id}."""
    status: Literal["approved", "retired"] = Field(
        ...,
        description="Target status. draft→approved (clinical_lead), approved→retired (admin), retired→approved (admin).",
    )


def _apply_rule_status_change(
    rule_id: int,
    target_status: Literal["approved", "retired"],
    current_user: AdminUser,
    background_tasks: BackgroundTasks,
) -> RuleActionResponse:
    rule = get_constraint_rule(rule_id)
    if not rule:
        raise HTTPException(status_code=404, detail="Constraint rule not found")

    current_status = rule["status"]
    if current_status == target_status:
        raise HTTPException(status_code=400, detail=f"Rule is already {target_status}")

    if target_status == "approved":
        if current_status == "draft":
            if "clinical_lead" not in current_user.roles:
                raise HTTPException(status_code=403, detail="User does not have the required 'clinical_lead' role")
            success = approve_constraint_rule(rule_id, current_user.id)
            message = "Rule approved successfully."
            details_keys = ("approved_at", "approved_by")
        elif current_status == "retired":
            if "admin" not in current_user.roles:
                raise HTTPException(status_code=403, detail="User does not have the required 'admin' role")
            success = unretire_constraint_rule(rule_id, current_user.id)
            message = "Constraint rule has been restored to 'approved' status."
            details_keys = ("approved_at", "approved_by")
        else:
            raise HTTPException(
                status_code=400,
                detail=f"Cannot transition from {current_status} to approved",
            )
    else:
        if current_status != "approved":
            raise HTTPException(
                status_code=400,
                detail=f"Can only retire approved rules, this one is {current_status}",
            )
        if "admin" not in current_user.roles:
            raise HTTPException(status_code=403, detail="User does not have the required 'admin' role")
        success = retire_constraint_rule(rule_id, current_user.id)
        message = "Constraint rule retired and no longer used in recommendations."
        details_keys = ("retired_at", "retired_by")

    if not success:
        raise HTTPException(status_code=500, detail=f"Failed to update constraint rule status to {target_status}")

    background_tasks.add_task(invalidate_constraint_cache)
    updated = get_constraint_rule(rule_id)
    return RuleActionResponse(
        id=rule_id,
        constraint_id=updated["constraint_id"],
        status=updated["status"],
        message=message,
        details={key: updated[key] for key in details_keys},
    )


@router.get("", response_model=ConstraintRuleListResponse)
def list_constraint_rules(
    status: str | None = Query(None, description="Filter by status: draft, approved, retired"),
    limit: int = Query(100, ge=1, le=500),
    current_user: AdminUser = Depends(require_role("clinical_lead")),
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
def get_constraint_rule_versions_endpoint(
    constraint_id: str,
    current_user: AdminUser = Depends(require_role("clinical_lead")),
) -> ConstraintRuleVersionListResponse:
    """Get all versions of a specific constraint rule by its constraint_id."""
    versions = get_constraint_rule_versions(constraint_id)
    if not versions:
        raise HTTPException(status_code=404, detail="Constraint rule not found")
    return ConstraintRuleVersionListResponse(items=[ConstraintRuleVersionItem(**v) for v in versions])


@router.get("/rules/{rule_id}", response_model=ConstraintRuleResponse)
def get_constraint_rule_endpoint(
    rule_id: int,
    current_user: AdminUser = Depends(require_role("clinical_lead")),
) -> ConstraintRuleResponse:
    """Get details of a specific constraint rule."""
    rule = get_constraint_rule(rule_id)
    if not rule:
        raise HTTPException(status_code=404, detail="Constraint rule not found")
    return ConstraintRuleResponse(**rule)


@router.patch("/rules/{rule_id}", response_model=RuleActionResponse)
def update_constraint_rule_status(
    rule_id: int,
    payload: ConstraintRuleStatusUpdate,
    background_tasks: BackgroundTasks,
    current_user: AdminUser = Depends(get_current_admin_user),
) -> RuleActionResponse:
    """Update a constraint rule version status."""
    return _apply_rule_status_change(rule_id, payload.status, current_user, background_tasks)


@router.post("/rules/{rule_id}/approve", response_model=RuleActionResponse, deprecated=True)
def approve_constraint_rule_endpoint(
    rule_id: int,
    background_tasks: BackgroundTasks,
    current_user: AdminUser = Depends(get_current_admin_user),
) -> RuleActionResponse:
    """[Deprecated] Use PATCH /rules/{rule_id} with {\"status\": \"approved\"}."""
    return _apply_rule_status_change(rule_id, "approved", current_user, background_tasks)


@router.post("/rules/{rule_id}/retire", response_model=RuleActionResponse, deprecated=True)
def retire_constraint_rule_endpoint(
    rule_id: int,
    background_tasks: BackgroundTasks,
    current_user: AdminUser = Depends(get_current_admin_user),
) -> RuleActionResponse:
    """[Deprecated] Use PATCH /rules/{rule_id} with {\"status\": \"retired\"}."""
    return _apply_rule_status_change(rule_id, "retired", current_user, background_tasks)


@router.post("/rules/{rule_id}/unretire", response_model=RuleActionResponse, deprecated=True)
def unretire_constraint_rule_endpoint(
    rule_id: int,
    background_tasks: BackgroundTasks,
    current_user: AdminUser = Depends(get_current_admin_user),
) -> RuleActionResponse:
    """[Deprecated] Use PATCH /rules/{rule_id} with {\"status\": \"approved\"}."""
    return _apply_rule_status_change(rule_id, "approved", current_user, background_tasks)


@router.get("/{constraint_id}/history", response_model=ConstraintRuleHistoryResponse)
def get_constraint_rule_history_endpoint(
    constraint_id: str,
    current_user: AdminUser = Depends(require_role("clinical_lead")),
) -> ConstraintRuleHistoryResponse:
    """Get the status change history of a specific constraint rule."""
    # First, check if any version of the rule exists to provide a proper 404 error
    rule_exists = rule_with_constraint_id_exists(constraint_id)
    if not rule_exists:
        raise HTTPException(status_code=404, detail="Constraint rule not found")
    
    history_items = read_constraint_rule_history(constraint_id)
    return ConstraintRuleHistoryResponse(items=history_items)
