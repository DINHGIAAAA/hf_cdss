"""Shared admin route dependencies."""

from fastapi import Depends, HTTPException
from pydantic import BaseModel

from app.api.routes.auth import oauth2_scheme
from app.core.token_service import TokenValidationError, resolve_active_user_from_token, token_validation_to_http


class AdminUser(BaseModel):
    id: str
    username: str | None = None
    roles: list[str]


async def get_current_admin_user(token: str = Depends(oauth2_scheme)) -> AdminUser:
    try:
        user = await resolve_active_user_from_token(token)
    except TokenValidationError as exc:
        raise token_validation_to_http(exc) from exc

    return AdminUser(id=user["id"], username=user.get("username"), roles=user["roles"])


def require_role(required_role: str):
    async def role_checker(user: AdminUser = Depends(get_current_admin_user)) -> AdminUser:
        if required_role not in user.roles:
            raise HTTPException(
                status_code=403,
                detail=f"User does not have the required '{required_role}' role",
            )
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
