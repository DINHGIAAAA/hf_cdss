import logging

from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.config import settings
from app.schemas.common import ErrorDetail, ErrorResponse


logger = logging.getLogger(__name__)


def _request_id(request: Request) -> str | None:
    return getattr(request.state, "request_id", None)


def _safe_validation_errors(exc: RequestValidationError) -> list[dict]:
    errors = exc.errors()
    sanitized = []
    for error in errors:
        item = dict(error)
        item.pop("input", None)
        sanitized.append(item)
    return sanitized


def _error_details(request: Request, detail) -> dict | None:
    details = {"request_id": _request_id(request)} if _request_id(request) else {}
    if isinstance(detail, dict):
        details.update(detail)
    return details or None


async def http_exception_handler(
    request: Request,
    exc: StarletteHTTPException,
) -> JSONResponse:
    logger.warning(
        "HTTP error on %s %s request_id=%s status=%s detail=%s",
        request.method,
        request.url.path,
        _request_id(request),
        exc.status_code,
        exc.detail,
    )
    payload = ErrorResponse(
        error=ErrorDetail(
            code=f"http_{exc.status_code}",
            message=str(exc.detail),
            details=_error_details(request, exc.detail),
        )
    )
    return JSONResponse(status_code=exc.status_code, content=payload.model_dump())


async def validation_exception_handler(
    request: Request,
    exc: RequestValidationError,
) -> JSONResponse:
    errors = _safe_validation_errors(exc)
    logger.warning(
        "Validation error on %s %s request_id=%s errors=%s",
        request.method,
        request.url.path,
        _request_id(request),
        errors,
    )
    payload = ErrorResponse(
        error=ErrorDetail(
            code="validation_error",
            message="Request validation failed.",
            details={"request_id": _request_id(request), "errors": errors},
        )
    )
    return JSONResponse(status_code=422, content=payload.model_dump())


async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.exception("Unhandled error on %s %s request_id=%s", request.method, request.url.path, _request_id(request))
    payload = ErrorResponse(
        error=ErrorDetail(
            code="internal_server_error",
            message="An unexpected error occurred.",
            details={"request_id": _request_id(request)} if _request_id(request) else None,
        )
    )
    return JSONResponse(status_code=500, content=payload.model_dump())

