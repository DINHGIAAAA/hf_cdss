import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api.router import api_router
from app.core.config import settings
from app.core.exceptions import (
    http_exception_handler,
    unhandled_exception_handler,
    validation_exception_handler,
)
from app.core.logging import configure_logging
from app.modules.datastores.service import bootstrap_datastores


configure_logging()


@asynccontextmanager
async def lifespan(_: FastAPI):
    if settings.datastore_bootstrap_on_startup:
        await asyncio.to_thread(bootstrap_datastores)
    yield


app = FastAPI(
    title=settings.project_name,
    version=settings.version,
    description="Heart failure medication decision support API.",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.add_exception_handler(StarletteHTTPException, http_exception_handler)
app.add_exception_handler(RequestValidationError, validation_exception_handler)
app.add_exception_handler(Exception, unhandled_exception_handler)
app.include_router(api_router)


@app.get("/")
def root() -> dict:
    return {
        "service": settings.project_name,
        "version": settings.version,
        "status": "ok",
        "docs": "/docs",
        "endpoints": [
            "GET /health",
            "GET /health/dependencies",
            "GET /version",
            "POST /normalize",
            "POST /risks",
            "POST /constraints",
            "POST /recommend",
            "POST /dose/check",
            "POST /interaction/check",
            "GET /rules",
            "POST /graphrag/context",
            "POST /verify",
            "POST /llm/answer",
            "GET /audit/{case_id}",
        ],
    }
