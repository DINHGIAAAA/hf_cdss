from fastapi import APIRouter, HTTPException

from app.core.config import settings
from app.modules.datastores.service import datastore_status
from app.schemas.common import DependencyHealthResponse, HealthResponse, VersionResponse


router = APIRouter()


@router.get("/health", response_model=HealthResponse)
def health_check() -> HealthResponse:
    return HealthResponse(status="ok", service=settings.project_name)


@router.get("/health/live", response_model=HealthResponse)
def liveness() -> HealthResponse:
    return HealthResponse(status="ok", service=settings.project_name)


@router.get("/health/ready", response_model=DependencyHealthResponse)
def readiness() -> DependencyHealthResponse:
    return dependency_health()


@router.get("/version", response_model=VersionResponse)
def version() -> VersionResponse:
    return VersionResponse(version=settings.version, environment=settings.environment)


@router.get("/health/dependencies", response_model=DependencyHealthResponse)
def dependency_health() -> DependencyHealthResponse:
    dependencies = datastore_status()
    status = "ok" if all(item["status"] == "ok" for item in dependencies.values()) else "degraded"
    response = DependencyHealthResponse(
        status=status,
        dependencies=dependencies,
    )
    if status != "ok":
        raise HTTPException(status_code=503, detail=response.model_dump())
    return response
