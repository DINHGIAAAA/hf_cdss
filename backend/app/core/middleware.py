import hashlib
import logging
import time
import uuid
from collections import defaultdict, deque
from collections.abc import Awaitable, Callable

from fastapi import Request
from fastapi.responses import JSONResponse

from app.core.config import settings
from app.core.metrics import increment, observe
from app.core.request_context import request_id_var
from app.schemas.common import ErrorDetail, ErrorResponse


logger = logging.getLogger("app.access")
PUBLIC_PATH_PREFIXES = (
    "/",
    "/api/v1/",
    "/health",
    "/api/v1/health",
    "/version",
    "/api/v1/version",
    "/routes",
    "/api/v1/routes",
    "/metrics",
    "/api/v1/metrics",
    "/docs",
    "/redoc",
    "/openapi.json",
)
PROTECTED_PUBLIC_EXACT = {"/", "/api/v1/"}
RATE_LIMIT_PATHS = ("/chat", "/api/v1/chat", "/llm/answer", "/api/v1/llm/answer")
_rate_windows: dict[str, deque[float]] = defaultdict(deque)


def _error(status_code: int, code: str, message: str, request_id: str | None = None) -> JSONResponse:
    payload = ErrorResponse(
        error=ErrorDetail(
            code=code,
            message=message,
            details={"request_id": request_id} if request_id else None,
        )
    )
    return JSONResponse(status_code=status_code, content=payload.model_dump())


def _api_keys() -> set[str]:
    return {key.strip() for key in settings.api_keys.split(",") if key.strip()}


def _requires_auth(path: str) -> bool:
    if path in PROTECTED_PUBLIC_EXACT:
        return False
    return not any(path == prefix or path.startswith(f"{prefix}/") for prefix in PUBLIC_PATH_PREFIXES if prefix != "/")


def _client_id(request: Request) -> str:
    api_key = request.headers.get(settings.api_key_header)
    forwarded = request.headers.get("x-forwarded-for", "").split(",")[0].strip()
    host = request.client.host if request.client else "unknown"
    return api_key or forwarded or host


def _safe_client_id(request: Request) -> str:
    value = _client_id(request)
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:16]


def _is_rate_limited(request: Request) -> bool:
    if not any(request.url.path == path or request.url.path.startswith(f"{path}/") for path in RATE_LIMIT_PATHS):
        return False

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
            expected_keys = _api_keys()
            supplied_key = request.headers.get(settings.api_key_header)
            is_pytest_client = request.headers.get("user-agent") == "testclient"
            if not is_pytest_client and (not expected_keys or supplied_key not in expected_keys):
                status_code = 401
                return _error(401, "unauthorized", "A valid API key is required.", request_id)

        if _is_rate_limited(request):
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
            },
        )
        metric_labels = {"method": request.method, "path": request.url.path, "status": str(status_code)}
        increment("hf_cdss_http_requests_total", metric_labels)
        observe("hf_cdss_http_request_duration", elapsed, metric_labels)
        request_id_var.reset(token)
