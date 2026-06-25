import pytest

from fastapi.testclient import TestClient

from app.core.config import settings
from app.main import app


API_PREFIX = "/api/v1"
TEST_API_KEY = "test-api-key"


def api_path(path: str) -> str:
    normalized = path if path.startswith("/") else f"/{path}"
    if normalized.startswith(API_PREFIX):
        return normalized
    return f"{API_PREFIX}{normalized}"


@pytest.fixture(autouse=True)
def _configure_test_auth(monkeypatch) -> None:
    monkeypatch.setattr(settings, "api_keys", TEST_API_KEY)
    monkeypatch.setattr(settings, "environment", "test")


@pytest.fixture
def client() -> TestClient:
    return TestClient(app, headers={settings.api_key_header: TEST_API_KEY})


@pytest.fixture
def unauthenticated_client() -> TestClient:
    return TestClient(app)
