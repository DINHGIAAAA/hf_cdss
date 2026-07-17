from fastapi import APIRouter, HTTPException

from app.core.config import settings
from app.modules.datastores.bootstrap import bootstrap_is_complete, bootstrap_status
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


def _get_datastore_health() -> dict[str, dict]:
    """Get health status for all datastores."""
    return datastore_status()


def _get_dependency_overall_status(dependencies: dict[str, dict]) -> str:
    """Determine overall status based on dependency health checks.

    Critical dependencies: postgres, chroma (required for core functionality)
    Non-critical dependencies: redis, s3, neo4j, artifacts (degraded if unavailable)
    """
    critical = ["postgres", "chroma"]
    non_critical = ["redis", "s3", "neo4j", "artifacts", "dose_rules"]

    # Check critical dependencies
    for name in critical:
        if name in dependencies:
            status = dependencies[name].get("status", "")
            if status != "ok" and status != "disabled":
                return "degraded"

    # Check if any non-critical are error states (not just unavailable)
    for name in non_critical:
        if name in dependencies:
            status = dependencies[name].get("status", "")
            if status == "error":
                return "degraded"

    return "ok"


@router.get("/health/dependencies", response_model=DependencyHealthResponse)
def dependency_health() -> DependencyHealthResponse:
    bootstrap = bootstrap_status()
    if not bootstrap_is_complete():
        dependencies = {"bootstrap": bootstrap}
        response = DependencyHealthResponse(status="starting", dependencies=dependencies)
        raise HTTPException(status_code=503, detail=response.model_dump())

    # Get datastore status including new Redis and S3 checks
    dependencies = {"bootstrap": bootstrap, **_get_datastore_health()}

    # Determine status based on critical vs non-critical dependencies
    status = _get_dependency_overall_status(dependencies)

    response = DependencyHealthResponse(
        status=status,
        dependencies=dependencies,
    )

    # Only return 503 if critical dependencies are down
    if status == "degraded":
        # Check if critical dependencies are actually down
        critical_down = False
        for name in ["postgres", "chroma"]:
            if name in dependencies and dependencies[name].get("status") not in ["ok", "disabled"]:
                critical_down = True
                break

        if critical_down:
            raise HTTPException(status_code=503, detail=response.model_dump())

    return response


@router.get("/health/datastores")
def datastore_health() -> dict[str, dict]:
    """Detailed health check for all datastores (Redis, ChromaDB, Neo4j, S3, PostgreSQL)."""
    return _get_datastore_health()
