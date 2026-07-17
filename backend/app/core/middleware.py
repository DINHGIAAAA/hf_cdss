import hashlib
import logging
import time
import uuid
from collections import defaultdict, deque
from collections.abc import Awaitable, Callable

from fastapi import Request
from fastapi.responses import JSONResponse

from app.core.auth_credentials import is_authorized_request
from app.core.config import settings
from app.core.metrics import increment, observe
from app.core.redis_client import redis_client
from app.core.request_context import request_id_var
from app.schemas.common import ErrorDetail, ErrorResponse


logger = logging.getLogger("app.access")

API_PREFIX = settings.api_prefix.rstrip("/")

PUBLIC_PATH_EXACT = {
    "/",
    "/routes",
    f"{API_PREFIX}/routes",
}

PUBLIC_PATH_PREFIXES = (
    "/docs",
    "/redoc",
    "/openapi.json",
    f"{API_PREFIX}/health",
    f"{API_PREFIX}/version",
    f"{API_PREFIX}/metrics",
    f"{API_PREFIX}/auth/login",
    "/api/auth/login",
)

RATE_LIMIT_PATHS = (
    f"{API_PREFIX}/chat",
    f"{API_PREFIX}/chat/stream",
    f"{API_PREFIX}/llm/answer",
)

ADMIN_RATE_LIMIT_PATHS = (
    f"{API_PREFIX}/admin",
)

LOGIN_RATE_LIMIT_PATHS = (
    f"{API_PREFIX}/auth/login",
    "/api/auth/login",
)

# Fallback in-memory rate limiting (used when Redis is unavailable)
_rate_windows: dict[str, deque[float]] = defaultdict(deque)
_admin_rate_windows: dict[str, deque[float]] = defaultdict(deque)
_login_rate_windows: dict[str, deque[float]] = defaultdict(deque)
_use_redis_fallback = False


def _error(status_code: int, code: str, message: str, request_id: str | None = None) -> JSONResponse:
    payload = ErrorResponse(
        error=ErrorDetail(
            code=code,
            message=message,
            details={"request_id": request_id} if request_id else None,
        )
    )
    return JSONResponse(status_code=status_code, content=payload.model_dump())


def _matches_public_prefix(path: str, prefix: str) -> bool:
    normalized = prefix.rstrip("/")
    return path == normalized or path.startswith(f"{normalized}/")


def _is_public_path(path: str) -> bool:
    if path in PUBLIC_PATH_EXACT:
        return True
    return any(_matches_public_prefix(path, prefix) for prefix in PUBLIC_PATH_PREFIXES)


def _requires_auth(path: str) -> bool:
    return not _is_public_path(path)


def _client_id(request: Request) -> str:
    api_key = request.headers.get(settings.api_key_header)
    forwarded = request.headers.get("x-forwarded-for", "").split(",")[0].strip()
    host = request.client.host if request.client else "unknown"
    return api_key or forwarded or host


def _safe_client_id(request: Request) -> str:
    value = _client_id(request)
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:16]


def _rate_limit_key(prefix: str, request: Request) -> str:
    """Generate rate limit key with prefix."""
    return f"ratelimit:{prefix}:{_safe_client_id(request)}:{request.url.path}"


async def _is_admin_rate_limited(request: Request) -> bool:
    if not any(
        request.url.path == path or request.url.path.startswith(f"{path}/") for path in ADMIN_RATE_LIMIT_PATHS
    ):
        return False

    window = max(1, settings.admin_rate_limit_window_seconds)
    limit = max(1, settings.admin_rate_limit_requests)
    key = _rate_limit_key("admin", request)

    try:
        count, _ = await redis_client.incr_with_expiry(key, window)
        return count > limit
    except Exception:
        # Fallback to in-memory if Redis fails
        return _is_admin_rate_limited_memory(request)


def _is_admin_rate_limited_memory(request: Request) -> bool:
    """In-memory fallback for admin rate limiting."""
    global _use_redis_fallback
    _use_redis_fallback = True
    now = time.monotonic()
    window = max(1, settings.admin_rate_limit_window_seconds)
    limit = max(1, settings.admin_rate_limit_requests)
    key = f"{_client_id(request)}:{request.url.path}"
    entries = _admin_rate_windows[key]
    while entries and now - entries[0] > window:
        entries.popleft()
    if len(entries) >= limit:
        return True
    entries.append(now)
    return False


async def _is_rate_limited(request: Request) -> bool:
    if not any(request.url.path == path or request.url.path.startswith(f"{path}/") for path in RATE_LIMIT_PATHS):
        return False

    window = max(1, settings.rate_limit_window_seconds)
    limit = max(1, settings.rate_limit_requests)
    key = _rate_limit_key("api", request)

    try:
        count, _ = await redis_client.incr_with_expiry(key, window)
        return count > limit
    except Exception:
        # Fallback to in-memory if Redis fails
        return _is_rate_limited_memory(request)


def _is_rate_limited_memory(request: Request) -> bool:
    """In-memory fallback for API rate limiting."""
    global _use_redis_fallback
    _use_redis_fallback = True
    now = time.monotonic()
    window = max(1, settings.rate_limit_window_seconds)
    limit = max(1, settings.rate_limit_requests)
    key = f"{_client_id(request)}:{request.url.path}"
    entries = _rate_windows[key]
    while entries and now - entries[0] > window:
        entries.popleft()
    if len(entries) >= limit:
        return True
    entries.append(now)
    return False


async def _is_login_rate_limited(request: Request) -> bool:
    if not any(request.url.path == path or request.url.path.startswith(f"{path}/") for path in LOGIN_RATE_LIMIT_PATHS):
        return False

    window = max(1, settings.auth_login_rate_limit_window_seconds)
    limit = max(1, settings.auth_login_rate_limit_requests)
    key = _rate_limit_key("login", request)

    try:
        count, _ = await redis_client.incr_with_expiry(key, window)
        return count > limit
    except Exception:
        # Fallback to in-memory if Redis fails
        return _is_login_rate_limited_memory(request)


def _is_login_rate_limited_memory(request: Request) -> bool:
    """In-memory fallback for login rate limiting."""
    global _use_redis_fallback
    _use_redis_fallback = True
    now = time.monotonic()
    window = max(1, settings.auth_login_rate_limit_window_seconds)
    limit = max(1, settings.auth_login_rate_limit_requests)
    key = f"{_client_id(request)}:{request.url.path}"
    entries = _login_rate_windows[key]
    while entries and now - entries[0] > window:
        entries.popleft()
    if len(entries) >= limit:
        return True
    entries.append(now)
    return False


async def production_guard_middleware(
    request: Request,
    call_next: Callable[[Request], Awaitable],
):
    request_id = request.headers.get("x-request-id") or str(uuid.uuid4())
    request.state.request_id = request_id
    token = request_id_var.set(request_id)
    started = time.perf_counter()
    status_code = 500
    try:
        content_length = request.headers.get("content-length")
        if content_length and int(content_length) > settings.max_request_body_bytes:
            status_code = 413
            return _error(413, "request_too_large", "Request body is too large.", request_id)

        if request.method != "OPTIONS" and _requires_auth(request.url.path):
            if not await is_authorized_request(request):
                status_code = 401
                return _error(
                    401,
                    "unauthorized",
                    "A valid API key or authenticated session is required.",
                    request_id,
                )

        if await _is_login_rate_limited(request):
            status_code = 429
            return _error(429, "rate_limited", "Too many login attempts. Please retry later.", request_id)

        if await _is_admin_rate_limited(request):
            status_code = 429
            return _error(429, "rate_limited", "Too many admin requests. Please retry later.", request_id)

        if await _is_rate_limited(request):
            status_code = 429
            return _error(429, "rate_limited", "Too many requests. Please retry later.", request_id)

        response = await call_next(request)
        status_code = response.status_code
        response.headers["x-request-id"] = request_id
        return response
    finally:
        elapsed = time.perf_counter() - started
        logger.info(
            "request completed",
            extra={
                "event": "http_request",
                "method": request.method,
                "path": request.url.path,
                "status_code": status_code,
                "duration_ms": round(elapsed * 1000, 2),
                "client": _safe_client_id(request),
                "ratelimit_fallback": _use_redis_fallback,
            },
        )
        metric_labels = {"method": request.method, "path": request.url.path, "status": str(status_code)}
        increment("hf_cdss_http_requests_total", metric_labels)
        observe("hf_cdss_http_request_duration", elapsed, metric_labels)
        request_id_var.reset(token)
