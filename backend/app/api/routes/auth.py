from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from pydantic import BaseModel

from app.core.auth_credentials import access_token_from_request, is_login_enabled
from app.core.config import settings
from app.core.jwt import jwt
from app.core.token_service import (
    TokenValidationError,
    block_access_token,
    resolve_active_user_from_token,
    token_validation_to_http,
)
from app.modules.datastores.users import authenticate_user

router = APIRouter(prefix="/auth", tags=["auth"])

oauth2_scheme = OAuth2PasswordBearer(
    tokenUrl=f"{settings.api_prefix}/auth/login",
    auto_error=False,
)


class Token(BaseModel):
    token_type: str
    expires_in: int


class AuthUser(BaseModel):
    id: str
    username: str
    display_name: str | None = None
    roles: list[str]


def create_access_token(data: dict, expires_delta: timedelta | None = None) -> tuple[str, int]:
    to_encode = data.copy()
    now = datetime.now(timezone.utc)
    if expires_delta:
        expire = now + expires_delta
    else:
        expire = now + timedelta(minutes=settings.jwt_access_token_expire_minutes)
    expires_in = int((expire - now).total_seconds())
    to_encode.update({"iat": now, "exp": expire, "sub": data["sub"]})
    encoded_jwt = jwt.encode(to_encode, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)
    return encoded_jwt, expires_in


def set_auth_cookie(response: Response, access_token: str, expires_in: int) -> None:
    response.set_cookie(
        key=settings.jwt_cookie_name,
        value=access_token,
        httponly=True,
        secure=settings.jwt_cookie_secure,
        samesite=settings.jwt_cookie_samesite,
        max_age=expires_in,
        path="/",
    )


def clear_auth_cookie(response: Response) -> None:
    response.delete_cookie(
        key=settings.jwt_cookie_name,
        path="/",
        secure=settings.jwt_cookie_secure,
        samesite=settings.jwt_cookie_samesite,
    )


async def get_access_token(request: Request, bearer: str | None = Depends(oauth2_scheme)) -> str:
    token = access_token_from_request(request, bearer)
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return token


async def get_current_user(token: str = Depends(get_access_token)) -> AuthUser:
    try:
        user = await resolve_active_user_from_token(token)
    except TokenValidationError as exc:
        raise token_validation_to_http(exc) from exc

    return AuthUser(
        id=user["id"],
        username=user["username"],
        display_name=user.get("display_name"),
        roles=user["roles"],
    )


@router.post("/login", response_model=Token)
async def login_for_access_token(
    response: Response,
    form_data: OAuth2PasswordRequestForm = Depends(),
):
    """Authenticate with username/password; session is stored in an httpOnly cookie."""
    if not is_login_enabled():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Login is disabled.",
        )

    user = authenticate_user(form_data.username, form_data.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    access_token, expires_in = create_access_token(data={"sub": user["id"], "roles": user["roles"]})
    set_auth_cookie(response, access_token, expires_in)
    return {"token_type": "bearer", "expires_in": expires_in}


@router.get("/me", response_model=AuthUser)
async def read_current_user(current_user: AuthUser = Depends(get_current_user)) -> AuthUser:
    return current_user


@router.post("/logout")
async def logout(
    request: Request,
    response: Response,
    bearer: str | None = Depends(oauth2_scheme),
):
    """Invalidate the current session cookie and blocklist the JWT until expiry."""
    token = access_token_from_request(request, bearer)
    if token:
        await block_access_token(token)
    clear_auth_cookie(response)
    return {"message": "Logged out successfully"}
