from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from app.api.routes.admin.deps import AdminUser, require_role
from app.core.roles import VALID_USER_ROLES
from app.modules.datastores.users import create_user, get_user_by_username, list_users, update_user


router = APIRouter(prefix="/users", tags=["admin", "users"])


class UserResponse(BaseModel):
    id: str
    username: str
    display_name: str | None = None
    roles: list[str]
    is_active: bool
    created_at: str | None = None
    updated_at: str | None = None


class UserListResponse(BaseModel):
    total: int
    items: list[UserResponse]


class CreateUserRequest(BaseModel):
    username: str = Field(..., min_length=2, max_length=64)
    password: str = Field(..., min_length=8, max_length=128)
    roles: list[str] = Field(default_factory=lambda: ["clinician"])
    display_name: str | None = Field(default=None, max_length=128)
    user_id: str | None = Field(default=None, max_length=128)


class UpdateUserRequest(BaseModel):
    password: str | None = Field(default=None, min_length=8, max_length=128)
    roles: list[str] | None = None
    display_name: str | None = Field(default=None, max_length=128)
    is_active: bool | None = None


def _validate_roles(roles: list[str]) -> list[str]:
    invalid = [role for role in roles if role not in VALID_USER_ROLES]
    if invalid:
        raise HTTPException(status_code=422, detail=f"Unsupported roles: {', '.join(invalid)}")
    if not roles:
        raise HTTPException(status_code=422, detail="At least one role is required")
    return roles


@router.get("", response_model=UserListResponse)
def list_users_endpoint(
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    current_user: AdminUser = Depends(require_role("admin")),
) -> UserListResponse:
    items = [UserResponse(**user) for user in list_users(limit=limit, offset=offset)]
    return UserListResponse(total=len(items), items=items)


@router.post("", response_model=UserResponse, status_code=201)
def create_user_endpoint(
    payload: CreateUserRequest,
    current_user: AdminUser = Depends(require_role("admin")),
) -> UserResponse:
    username = payload.username.strip()
    if get_user_by_username(username):
        raise HTTPException(status_code=409, detail="Username already exists")

    roles = _validate_roles(payload.roles)
    user_id = (payload.user_id or f"user_{username}").strip()
    created = create_user(
        user_id=user_id,
        username=username,
        password=payload.password,
        roles=roles,
        display_name=payload.display_name,
        is_active=True,
    )
    return UserResponse(**created)


@router.patch("/{user_id}", response_model=UserResponse)
def update_user_endpoint(
    user_id: str,
    payload: UpdateUserRequest,
    current_user: AdminUser = Depends(require_role("admin")),
) -> UserResponse:
    if user_id == current_user.id and payload.is_active is False:
        raise HTTPException(status_code=400, detail="You cannot deactivate your own account")

    roles = _validate_roles(payload.roles) if payload.roles is not None else None
    updated = update_user(
        user_id,
        roles=roles,
        display_name=payload.display_name,
        is_active=payload.is_active,
        password=payload.password,
    )
    if not updated:
        raise HTTPException(status_code=404, detail="User not found")
    return UserResponse(**updated)
