from typing import Any

from fastapi import HTTPException, status

from app.core.config import settings
from app.core.jwt import JWTError, jwt
from app.core.redis_client import redis_client
from app.modules.datastores.users import get_user_by_id


class TokenValidationError(Exception):
    def __init__(self, message: str, *, status_code: int = status.HTTP_401_UNAUTHORIZED) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code


async def is_token_blocklisted(token: str) -> bool:
    blocked = await redis_client.get(f"blocklist:{token}")
    return bool(blocked)


async def resolve_active_user_from_token(token: str) -> dict[str, Any]:
    if await is_token_blocklisted(token):
        raise TokenValidationError("Token has been revoked")

    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret_key,
            algorithms=[settings.jwt_algorithm],
        )
    except JWTError as exc:
        raise TokenValidationError("Invalid token") from exc

    user_id = payload.get("sub")
    if not user_id:
        raise TokenValidationError("Invalid token subject")

    user = get_user_by_id(str(user_id))
    if not user or not user["is_active"]:
        raise TokenValidationError("User is inactive or missing")

    return user


async def block_access_token(token: str) -> None:
    expire_seconds = settings.jwt_access_token_expire_minutes * 60
    await redis_client.setex(f"blocklist:{token}", expire_seconds, "true")


def token_validation_to_http(exc: TokenValidationError) -> HTTPException:
    return HTTPException(status_code=exc.status_code, detail=exc.message)
