import asyncio
import json
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.routing import APIRoute
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api.router import api_router
from app.core.config import settings
from app.core.exceptions import (
    http_exception_handler,
    unhandled_exception_handler,
    validation_exception_handler,
)
from app.core.logging import configure_logging
from app.core.middleware import production_guard_middleware
from app.modules.datastores.service import bootstrap_datastores
from app.schemas.common import RouteCatalogResponse, RouteInfo


configure_logging()

SUCCESSFUL_BOOTSTRAP_STATUSES = {"ok"}


def custom_generate_unique_id(route: APIRoute) -> str:
    methods = "_".join(sorted(route.methods or []))
    path = route.path_format.strip("/").replace("/", "_").replace("{", "").replace("}", "")
    return f"{route.name}_{methods}_{path or 'root'}"


@asynccontextmanager
async def lifespan(_: FastAPI):
    results = await asyncio.to_thread(bootstrap_datastores)
    failed = {
        name: result
        for name, result in results.items()
        if result.get("status") not in SUCCESSFUL_BOOTSTRAP_STATUSES
    }
    if failed:
        raise RuntimeError(f"Datastore bootstrap failed: {json.dumps(failed, ensure_ascii=False)}")
    yield


app = FastAPI(
    title=settings.project_name,
    version=settings.version,
    description="Heart failure medication decision support API.",
    lifespan=lifespan,
    generate_unique_id_function=custom_generate_unique_id,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.middleware("http")(production_guard_middleware)

app.add_exception_handler(StarletteHTTPException, http_exception_handler)
app.add_exception_handler(RequestValidationError, validation_exception_handler)
app.add_exception_handler(Exception, unhandled_exception_handler)
app.include_router(api_router)
app.include_router(api_router, prefix=settings.api_prefix)


def public_route_catalog() -> list[RouteInfo]:
    routes: list[RouteInfo] = []
    hidden_prefixes = ("/docs", "/redoc", "/openapi.json")
    for route in app.routes:
        if not isinstance(route, APIRoute):
            continue
        if route.path in {"/", "/routes", f"{settings.api_prefix}/routes"}:
            continue
        if any(route.path.startswith(prefix) for prefix in hidden_prefixes):
            continue
        routes.append(
            RouteInfo(
                path=route.path,
                methods=sorted(method for method in route.methods if method not in {"HEAD", "OPTIONS"}),
                name=route.name,
                tags=list(route.tags),
            )
        )
    return sorted(routes, key=lambda item: (item.path, item.methods))


@app.get("/routes", response_model=RouteCatalogResponse, tags=["system"])
def routes() -> RouteCatalogResponse:
    return RouteCatalogResponse(
        service=settings.project_name,
        version=settings.version,
        routes=public_route_catalog(),
    )


@app.get("/")
def root() -> dict:
    endpoints = [
        f"{method} {route.path}"
        for route in public_route_catalog()
        for method in route.methods
        if not route.path.startswith(settings.api_prefix)
    ]
    return {
        "service": settings.project_name,
        "version": settings.version,
        "status": "ok",
        "docs": "/docs",
        "api_prefix": settings.api_prefix,
        "endpoints": endpoints,
    }
