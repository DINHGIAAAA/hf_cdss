import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from collections.abc import Iterable

from fastapi.routing import APIRoute
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api.router import api_router
from app.api.routes import auth
from app.core.config import settings
from app.core.exceptions import (
    http_exception_handler,
    unhandled_exception_handler,
    validation_exception_handler,
)
from app.core.logging import configure_logging
from app.core.middleware import production_guard_middleware
from app.core.security_startup import validate_security_configuration
from app.modules.datastores.bootstrap import (
    shutdown_background_bootstrap,
    start_background_bootstrap,
)
from app.schemas.common import RouteCatalogResponse, RouteInfo


configure_logging()
logger = logging.getLogger(__name__)


def custom_generate_unique_id(route: APIRoute) -> str:
    methods = "_".join(sorted(route.methods or []))
    path = route.path_format.strip("/").replace("/", "_").replace("{", "").replace("}", "")
    return f"{route.name}_{methods}_{path or 'root'}"


@asynccontextmanager
async def lifespan(_: FastAPI):
    validate_security_configuration()
    await start_background_bootstrap()
    yield
    await shutdown_background_bootstrap()


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
app.include_router(api_router, prefix=settings.api_prefix)
# Legacy alias for clients still calling /api/auth/*
app.include_router(auth.router, prefix="/api")


def _iter_api_routes(routes_list) -> Iterable[APIRoute]:
    for route in routes_list:
        if isinstance(route, APIRoute):
            yield route
            continue
        nested = getattr(route, "routes", None)
        if nested:
            yield from _iter_api_routes(nested)
        nested_app = getattr(route, "app", None)
        if nested_app is not None and nested_app is not route:
            nested_routes = getattr(nested_app, "routes", None)
            if nested_routes:
                yield from _iter_api_routes(nested_routes)


def _catalog_from_openapi() -> list[RouteInfo]:
    hidden_paths = {"/", "/routes", f"{settings.api_prefix}/routes"}
    hidden_prefixes = ("/docs", "/redoc", "/openapi.json")
    catalog: dict[str, RouteInfo] = {}

    for path, path_item in app.openapi().get("paths", {}).items():
        if path in hidden_paths:
            continue
        if any(path.startswith(prefix) for prefix in hidden_prefixes):
            continue

        methods: list[str] = []
        operation: dict | None = None
        for method, details in path_item.items():
            if method.upper() in {"HEAD", "OPTIONS"} or not isinstance(details, dict):
                continue
            methods.append(method.upper())
            operation = operation or details

        if not methods:
            continue

        catalog[path] = RouteInfo(
            path=path,
            methods=sorted(methods),
            name=(operation or {}).get("operationId", ""),
            tags=list((operation or {}).get("tags") or []),
        )

    return sorted(catalog.values(), key=lambda item: (item.path, item.methods))


def public_route_catalog() -> list[RouteInfo]:
    routes: list[RouteInfo] = []
    hidden_paths = {"/", "/routes", f"{settings.api_prefix}/routes"}
    hidden_prefixes = ("/docs", "/redoc", "/openapi.json")
    for route in _iter_api_routes(app.routes):
        if route.path in hidden_paths:
            continue
        if any(route.path.startswith(prefix) for prefix in hidden_prefixes):
            continue
        routes.append(
            RouteInfo(
                path=route.path,
                methods=sorted(method for method in (route.methods or []) if method not in {"HEAD", "OPTIONS"}),
                name=route.name or "",
                tags=list(route.tags or []),
            )
        )

    if routes:
        return sorted(routes, key=lambda item: (item.path, item.methods))

    return _catalog_from_openapi()


@app.get("/routes", response_model=RouteCatalogResponse, tags=["system"])
def routes() -> RouteCatalogResponse:
    return RouteCatalogResponse(
        service=settings.project_name,
        version=settings.version,
        routes=public_route_catalog(),
    )


@app.get("/")
def root() -> dict:
    return {
        "service": settings.project_name,
        "version": settings.version,
        "status": "ok",
        "docs": "/docs",
        "api_prefix": settings.api_prefix,
        "routes_catalog": f"{settings.api_prefix}/routes",
    }
