"""Shared admin route dependencies."""

from fastapi import Depends, HTTPException, Request
from pydantic import BaseModel

from app.api.routes.auth import get_access_token, oauth2_scheme
from app.core.auth_credentials import access_token_from_request, has_valid_api_key
from app.core.token_service import TokenValidationError, resolve_active_user_from_token, token_validation_to_http


class AdminUser(BaseModel):
    id: str
    username: str | None = None
    roles: list[str]


_ADMIN_READER_ROLES = {"admin", "clinical_lead"}


async def get_current_admin_user(token: str = Depends(get_access_token)) -> AdminUser:
    try:
        user = await resolve_active_user_from_token(token)
    except TokenValidationError as exc:
        raise token_validation_to_http(exc) from exc

    return AdminUser(id=user["id"], username=user.get("username"), roles=user["roles"])


def ensure_role(user: AdminUser, required_role: str) -> None:
    """Raise 403 if *user* lacks *required_role* (for use outside Depends)."""
    if required_role not in user.roles:
        raise HTTPException(
            status_code=403,
            detail=f"User does not have the required '{required_role}' role",
        )


def require_role(required_role: str):
    async def role_checker(user: AdminUser = Depends(get_current_admin_user)) -> AdminUser:
        ensure_role(user, required_role)
        return user

    return role_checker


def require_any_role(*required_roles: str):
    allowed = set(required_roles)

    async def role_checker(user: AdminUser = Depends(get_current_admin_user)) -> AdminUser:
        if not any(role in user.roles for role in allowed):
            raise HTTPException(
                status_code=403,
                detail=f"User does not have any of the required roles: {', '.join(sorted(allowed))}",
            )
        return user

    return role_checker


require_admin_reader = require_any_role("admin", "clinical_lead")


async def require_catalog_reader(
    request: Request,
    bearer: str | None = Depends(oauth2_scheme),
) -> AdminUser | None:
    """Allow service API keys or admin/clinical_lead JWT sessions."""
    if has_valid_api_key(request):
        return None

    token = access_token_from_request(request, bearer)
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")

    try:
        user = await resolve_active_user_from_token(token)
    except TokenValidationError as exc:
        raise token_validation_to_http(exc) from exc

    if not any(role in user["roles"] for role in _ADMIN_READER_ROLES):
        raise HTTPException(
            status_code=403,
            detail="User does not have any of the required roles: admin, clinical_lead",
        )

    return AdminUser(id=user["id"], username=user.get("username"), roles=user["roles"])
