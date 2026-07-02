import pytest

from app.api.routes import health as health_routes
from app.modules.datastores import bootstrap as bootstrap_module
from app.tests.conftest import api_path


@pytest.fixture(autouse=True)
def _skip_heavy_bootstrap(monkeypatch) -> None:
    async def finish_immediately() -> None:
        bootstrap_module._bootstrap_results = {
            "artifacts": {"status": "ok"},
            "postgres": {"status": "ok"},
            "chroma": {"status": "ok"},
            "neo4j": {"status": "ok"},
        }
        bootstrap_module._bootstrap_phase = "completed"
        bootstrap_module._bootstrap_done.set()

    monkeypatch.setattr(bootstrap_module, "start_background_bootstrap", finish_immediately)


def test_readiness_returns_503_while_bootstrap_running(client, monkeypatch) -> None:
    monkeypatch.setattr(health_routes, "bootstrap_is_complete", lambda: False)
    monkeypatch.setattr(health_routes, "bootstrap_status", lambda: {"status": "running"})

    response = client.get(api_path("/health/ready"))

    assert response.status_code == 503
    assert response.json()["error"]["details"]["status"] == "starting"
    assert response.json()["error"]["details"]["dependencies"]["bootstrap"]["status"] == "running"


def test_health_live_while_bootstrap_running(client, monkeypatch) -> None:
    monkeypatch.setattr(bootstrap_module, "bootstrap_is_complete", lambda: False)

    response = client.get(api_path("/health"))

    assert response.status_code == 200
    assert response.json()["status"] == "ok"
