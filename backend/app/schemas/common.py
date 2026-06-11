from typing import Any

from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    status: str
    service: str


class VersionResponse(BaseModel):
    version: str
    environment: str


class DependencyHealthResponse(BaseModel):
    status: str
    dependencies: dict[str, dict[str, Any]]


class RouteInfo(BaseModel):
    path: str
    methods: list[str] = Field(default_factory=list)
    name: str
    tags: list[str] = Field(default_factory=list)


class RouteCatalogResponse(BaseModel):
    service: str
    version: str
    routes: list[RouteInfo]


class AuditHistoryResponse(BaseModel):
    case_id: str
    events: list[dict[str, Any]]
    status: str = "ok"


class ErrorDetail(BaseModel):
    code: str
    message: str
    details: Any | None = None


class ErrorResponse(BaseModel):
    error: ErrorDetail
