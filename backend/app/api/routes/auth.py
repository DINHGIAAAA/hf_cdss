import json
from datetime import datetime, timedelta, timezone
from functools import lru_cache

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from pydantic import BaseModel

from app.core.config import settings
from app.core.jwt import jwt

try:
    import redis.asyncio as redis
except ModuleNotFoundError:
    class _InMemoryRedisClient:
        def __init__(self) -> None:
            self._values: dict[str, str] = {}

        async def get(self, key: str):
            return self._values.get(key)

        async def setex(self, key: str, seconds: int, value: str):
            self._values[key] = value
            return True

    class _RedisFallback:
        @staticmethod
        def from_url(url: str, decode_responses: bool = True):
            return _InMemoryRedisClient()

    redis = _RedisFallback()

router = APIRouter(prefix="/auth", tags=["auth"])

redis_client = redis.from_url(settings.redis_url, decode_responses=True)
oauth2_scheme = OAuth2PasswordBearer(tokenUrl=f"{settings.api_prefix}/auth/login")


@lru_cache(maxsize=1)
def _dev_users() -> dict[str, dict[str, object]]:
    if not settings.auth_dev_login_enabled or not settings.auth_dev_users_json.strip():
        return {}
    return json.loads(settings.auth_dev_users_json)


class Token(BaseModel):
    access_token: str
    token_type: str


def create_access_token(data: dict, expires_delta: timedelta | None = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(minutes=settings.jwt_access_token_expire_minutes)
    to_encode.update({"exp": expire})

    encoded_jwt = jwt.encode(to_encode, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)
    return encoded_jwt


@router.post("/login", response_model=Token)
async def login_for_access_token(form_data: OAuth2PasswordRequestForm = Depends()):
    """
    Endpoint đăng nhập để lấy JWT Token.
    Tương thích hoàn toàn với nút 'Authorize' trên Swagger UI.
    """
    if not settings.auth_dev_login_enabled:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Dev login is disabled. Configure HF_CDSS_AUTH_DEV_LOGIN_ENABLED and user store.",
        )

    user = _dev_users().get(form_data.username)
    if not user or user["password"] != form_data.password:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Sai username hoặc password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    access_token = create_access_token(data={"sub": user["id"], "roles": user["roles"]})
    return {"access_token": access_token, "token_type": "bearer"}


@router.post("/logout")
async def logout(token: str = Depends(oauth2_scheme)):
    """
    Endpoint đăng xuất.
    Lưu token vào Redis blocklist với thời gian sống (TTL) bằng với thời hạn của token.
    """
    expire_seconds = settings.jwt_access_token_expire_minutes * 60
    await redis_client.setex(f"blocklist:{token}", expire_seconds, "true")
    return {"message": "Đăng xuất thành công, token đã bị vô hiệu hóa"}
