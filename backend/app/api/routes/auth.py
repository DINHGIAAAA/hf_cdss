from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from pydantic import BaseModel

from app.core.auth_credentials import is_login_enabled
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

oauth2_scheme = OAuth2PasswordBearer(tokenUrl=f"{settings.api_prefix}/auth/login")


class Token(BaseModel):
    access_token: str
    token_type: str


class AuthUser(BaseModel):
    id: str
    username: str
    display_name: str | None = None
    roles: list[str]


def create_access_token(data: dict, expires_delta: timedelta | None = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(minutes=settings.jwt_access_token_expire_minutes)
    to_encode.update({"exp": expire})

    encoded_jwt = jwt.encode(to_encode, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)
    return encoded_jwt


async def get_current_user(token: str = Depends(oauth2_scheme)) -> AuthUser:
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
async def login_for_access_token(form_data: OAuth2PasswordRequestForm = Depends()):
    """
    Đăng nhập bằng username/password lưu trong PostgreSQL.
    """
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

    access_token = create_access_token(data={"sub": user["id"], "roles": user["roles"]})
    return {"access_token": access_token, "token_type": "bearer"}


@router.get("/me", response_model=AuthUser)
async def read_current_user(current_user: AuthUser = Depends(get_current_user)) -> AuthUser:
    return current_user


@router.post("/logout")
async def logout(token: str = Depends(oauth2_scheme)):
    """
    Endpoint đăng xuất.
    Lưu token vào Redis blocklist với thời gian sống (TTL) bằng với thời hạn của token.
    """
    await block_access_token(token)
    return {"message": "Đăng xuất thành công, token đã bị vô hiệu hóa"}
