from fastapi import APIRouter

from app.core.config import settings
from app.modules.datastores.service import datastore_status
from app.schemas.common import HealthResponse, VersionResponse


router = APIRouter()


@router.get("/health", response_model=HealthResponse)
def health_check() -> HealthResponse:
    return HealthResponse(status="ok", service=settings.project_name)


@router.get("/version", response_model=VersionResponse)
def version() -> VersionResponse:
    return VersionResponse(version=settings.version, environment=settings.environment)


@router.get("/health/dependencies")
def dependency_health() -> dict:
    dependencies = datastore_status()
    return {
        "status": "ok" if all(item["status"] == "ok" for item in dependencies.values()) else "degraded",
        "dependencies": dependencies,
    }

