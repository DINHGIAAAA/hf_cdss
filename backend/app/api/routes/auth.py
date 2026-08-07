from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, File, HTTPException, Request, Response, UploadFile, status
from fastapi.responses import Response as StarletteResponse
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from pydantic import BaseModel, Field, model_validator

from app.core.auth_credentials import access_token_from_request, is_login_enabled
from app.core.passwords import verify_password
from app.core.config import settings
from app.core.jwt import jwt
from app.core.token_service import (
    TokenValidationError,
    block_access_token,
    resolve_active_user_from_token,
    token_validation_to_http,
)
from app.modules.datastores.users import (
    authenticate_user,
    get_user_by_id,
    set_user_avatar_storage_key,
    update_user,
)
from app.modules.profile_avatars import (
    AVATAR_API_PATH,
    delete_avatar_file,
    read_avatar_file,
    save_avatar_file,
)

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
    avatar_url: str | None = None
    avatar_version: str | None = None


class UpdateProfileRequest(BaseModel):
    display_name: str | None = Field(default=None, max_length=128)
    current_password: str | None = Field(default=None, min_length=1, max_length=128)
    new_password: str | None = Field(default=None, min_length=8, max_length=128)

    @model_validator(mode="after")
    def validate_password_change(self) -> "UpdateProfileRequest":
        if self.new_password and not self.current_password:
            raise ValueError("current_password is required when setting new_password")
        return self


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

    return _auth_user_from_db_user(user)


def _auth_user_from_db_user(user: dict) -> AuthUser:
    has_avatar = bool(user.get("avatar_storage_key"))
    return AuthUser(
        id=user["id"],
        username=user["username"],
        display_name=user.get("display_name"),
        roles=user["roles"],
        avatar_url=AVATAR_API_PATH if has_avatar else None,
        avatar_version=user.get("updated_at") if has_avatar else None,
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


def _auth_user_from_row(row: dict) -> AuthUser:
    has_avatar = bool(row.get("avatar_storage_key"))
    return AuthUser(
        id=row["id"],
        username=row["username"],
        display_name=row.get("display_name"),
        roles=row["roles"],
        avatar_url=AVATAR_API_PATH if has_avatar else None,
        avatar_version=row.get("updated_at") if has_avatar else None,
    )


@router.patch("/me", response_model=AuthUser)
async def update_profile(
    payload: UpdateProfileRequest,
    current_user: AuthUser = Depends(get_current_user),
) -> AuthUser:
    if payload.display_name is None and not payload.new_password:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No profile fields to update",
        )

    if payload.new_password:
        stored = get_user_by_id(current_user.id)
        if not stored or not verify_password(payload.current_password or "", stored["password_hash"]):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Current password is incorrect",
            )

    updated = update_user(
        current_user.id,
        display_name=payload.display_name,
        password=payload.new_password,
    )
    if not updated:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    fresh = get_user_by_id(current_user.id)
    if not fresh:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return _auth_user_from_db_user(fresh)


@router.get("/me/avatar")
async def get_my_avatar(current_user: AuthUser = Depends(get_current_user)) -> StarletteResponse:
    stored = get_user_by_id(current_user.id)
    if not stored or not stored.get("avatar_storage_key"):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No avatar")

    payload = read_avatar_file(stored["avatar_storage_key"])
    if not payload:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No avatar")

    data, media_type = payload
    return StarletteResponse(
        content=data,
        media_type=media_type,
        headers={"Cache-Control": "private, max-age=300"},
    )


@router.post("/me/avatar", response_model=AuthUser)
async def upload_my_avatar(
    file: UploadFile = File(...),
    current_user: AuthUser = Depends(get_current_user),
) -> AuthUser:
    raw = await file.read()
    try:
        storage_key = save_avatar_file(
            user_id=current_user.id,
            data=raw,
            media_type=file.content_type or "",
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    updated = set_user_avatar_storage_key(current_user.id, storage_key)
    if not updated:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    return _auth_user_from_row(updated)


@router.delete("/me/avatar", response_model=AuthUser)
async def delete_my_avatar(current_user: AuthUser = Depends(get_current_user)) -> AuthUser:
    stored = get_user_by_id(current_user.id)
    if not stored:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    delete_avatar_file(stored.get("avatar_storage_key"))
    updated = set_user_avatar_storage_key(current_user.id, None)
    if not updated:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return _auth_user_from_row(updated)


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
