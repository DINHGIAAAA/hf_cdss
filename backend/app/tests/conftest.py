import pytest

from fastapi.testclient import TestClient

from app.main import app


API_PREFIX = "/api/v1"


def api_path(path: str) -> str:
    normalized = path if path.startswith("/") else f"/{path}"
    if normalized.startswith(API_PREFIX):
        return normalized
    return f"{API_PREFIX}{normalized}"


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)
