from fastapi import Request

from app.core.config import settings
from app.core.token_service import TokenValidationError, resolve_active_user_from_token


def is_login_enabled() -> bool:
    return settings.auth_login_enabled


def api_keys() -> set[str]:
    return {key.strip() for key in settings.api_keys.split(",") if key.strip()}


def bearer_token(request: Request) -> str | None:
    authorization = request.headers.get("authorization", "")
    if not authorization.lower().startswith("bearer "):
        return None
    token = authorization[7:].strip()
    return token or None


def access_token_from_request(request: Request, bearer: str | None = None) -> str | None:
    cookie_token = request.cookies.get(settings.jwt_cookie_name)
    if cookie_token:
        return cookie_token
    if bearer:
        return bearer
    return bearer_token(request)


def has_valid_api_key(request: Request) -> bool:
    keys = api_keys()
    if not keys:
        return False
    supplied = request.headers.get(settings.api_key_header)
    return supplied in keys


async def has_valid_bearer_jwt(request: Request) -> bool:
    token = access_token_from_request(request)
    if not token:
        return False
    try:
        await resolve_active_user_from_token(token)
        return True
    except TokenValidationError:
        return False


async def is_authorized_request(request: Request) -> bool:
    if has_valid_api_key(request):
        return True
    return await has_valid_bearer_jwt(request)
