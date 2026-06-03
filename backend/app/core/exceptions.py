import logging

from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.schemas.common import ErrorDetail, ErrorResponse


logger = logging.getLogger(__name__)


async def http_exception_handler(
    request: Request,
    exc: StarletteHTTPException,
) -> JSONResponse:
    logger.warning("HTTP error on %s %s: %s", request.method, request.url.path, exc.detail)
    payload = ErrorResponse(
        error=ErrorDetail(
            code=f"http_{exc.status_code}",
            message=str(exc.detail),
            details=None,
        )
    )
    return JSONResponse(status_code=exc.status_code, content=payload.model_dump())


async def validation_exception_handler(
    request: Request,
    exc: RequestValidationError,
) -> JSONResponse:
    logger.warning("Validation error on %s %s: %s", request.method, request.url.path, exc.errors())
    payload = ErrorResponse(
        error=ErrorDetail(
            code="validation_error",
            message="Request validation failed.",
            details=exc.errors(),
        )
    )
    return JSONResponse(status_code=422, content=payload.model_dump())


async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.exception("Unhandled error on %s %s", request.method, request.url.path)
    payload = ErrorResponse(
        error=ErrorDetail(
            code="internal_server_error",
            message="An unexpected error occurred.",
            details=None,
        )
    )
    return JSONResponse(status_code=500, content=payload.model_dump())

