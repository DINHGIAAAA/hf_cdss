import json
import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

os.environ.setdefault("HF_CDSS_ENVIRONMENT", "test")
os.environ.setdefault("HF_CDSS_API_KEYS", "test-api-key")
os.environ.setdefault("HF_CDSS_LLM_BASE_URL", "http://127.0.0.1:9/v1")
os.environ.setdefault("HF_CDSS_LLM_TIMEOUT_SECONDS", "1")
os.environ.setdefault("HF_CDSS_CLINICAL_INTAKE_LLM_TIMEOUT_SECONDS", "1")

from app.core.config import settings
from app.main import app
from app.modules.constraint_builder.service import invalidate_constraint_cache
from app.modules.interaction_checking.rule_loader import invalidate_interaction_rules_cache
from app.modules.datastores import bootstrap as bootstrap_module


API_PREFIX = "/api/v1"
TEST_API_KEY = "test-api-key"
_CONSTRAINTS_FIXTURE = (
    Path(__file__).resolve().parents[1] / "modules" / "constraint_builder" / "rules" / "constraints_v1.json"
)
_SAMPLE_CHUNK = {
    "chunk_id": "chunk_dapagliflozin_hf",
    "document_id": "dapagliflozin",
    "source_type": "drug_label",
    "section": "HEART FAILURE",
    "text": (
        "Dapagliflozin reduces heart failure hospitalization in HFrEF with renal benefits, "
        "eGFR monitoring, and hyperkalemia risk when combined with MRA therapy."
    ),
    "metadata": {
        "source_id": "dapagliflozin_label",
        "source_url": "https://example.test/dapagliflozin",
        "publisher": "DailyMed",
        "page": 1,
    },
}
_SAMPLE_RELATIONSHIPS = [
    {
        "relationship_id": "rel_mra_hyperkalemia",
        "source_id": "spironolactone",
        "source_type": "drug",
        "target_id": "hyperkalemia",
        "target_type": "condition",
        "relationship_type": "contraindicated_when",
        "metadata": {
            "claim_type": "safety",
            "search_text": "mra hyperkalemia egfr renal potassium risk",
        },
    },
    {
        "relationship_id": "rel_dapagliflozin_interaction",
        "source_id": "dapagliflozin",
        "source_type": "drug",
        "target_id": "insulin",
        "target_type": "drug",
        "relationship_type": "interacts_with",
        "metadata": {
            "claim_type": "drug_interaction",
            "search_text": "dapagliflozin insulin interaction hypoglycemia",
        },
    },
]

_CHAT_MESSAGES: list[dict] = []
_CHAT_DRAFTS: dict[str, dict] = {}


def api_path(path: str) -> str:
    normalized = path if path.startswith("/") else f"/{path}"
    if normalized.startswith(API_PREFIX):
        return normalized
    return f"{API_PREFIX}{normalized}"


def approved_constraint_rules_fixture() -> list[dict]:
    payload = json.loads(_CONSTRAINTS_FIXTURE.read_text(encoding="utf-8"))
    rules: list[dict] = []
    for index, rule in enumerate(payload, start=1):
        rules.append(
            {
                "id": index,
                "constraint_id": rule["constraint_id"],
                "version": 1,
                "target_drug_class": rule.get("target_drug_class"),
                "action": rule.get("action"),
                "reason": rule.get("reason", ""),
                "risk_names": list(rule.get("risk_names") or []),
                "severity_any": list(rule.get("severity_any") or []),
                "evidence_ref": rule.get("evidence_ref"),
                "clinical_sources": list(rule.get("clinical_sources") or []),
                "metadata": {"constraint_type": rule.get("constraint_type", "soft")},
            }
        )
    return rules


def _mark_bootstrap_complete() -> None:
    bootstrap_module._bootstrap_results = {
        "artifacts": {"status": "ok"},
        "postgres": {"status": "ok"},
        "chroma": {"status": "ok"},
        "neo4j": {"status": "ok"},
    }
    bootstrap_module._bootstrap_phase = "completed"
    bootstrap_module._bootstrap_done.set()


async def _finish_bootstrap_immediately() -> None:
    _mark_bootstrap_complete()


def _clear_graphrag_caches(graphrag_service) -> None:
    for name in (
        "load_chunks",
        "load_published_chunks",
        "load_staging_chunks",
        "load_relationships",
        "load_published_relationships",
        "load_staging_relationships",
    ):
        loader = getattr(graphrag_service, name, None)
        if loader is not None and hasattr(loader, "cache_clear"):
            loader.cache_clear()


def _patch_session_dependencies() -> None:
    from app.modules.graphrag import service as graphrag_service

    rules = approved_constraint_rules_fixture()
    chunks = [_SAMPLE_CHUNK]
    relationships = list(_SAMPLE_RELATIONSHIPS)

    bootstrap_module.start_background_bootstrap = _finish_bootstrap_immediately
    _mark_bootstrap_complete()

    def fake_datastore_status() -> dict:
        return {
            "artifacts": {"status": "ok"},
            "postgres": {"status": "ok"},
            "chroma": {"status": "ok"},
            "neo4j": {"status": "ok"},
        }

    def fake_get_user_by_id(user_id: str):
        return None

    def append_chat_message(row: dict) -> None:
        _CHAT_MESSAGES.append(row)

    def read_chat_messages(conversation_id: str) -> list[dict]:
        return [row for row in _CHAT_MESSAGES if row.get("conversation_id") == conversation_id]

    def upsert_patient_draft(row: dict) -> None:
        _CHAT_DRAFTS[row["conversation_id"]] = row

    def read_patient_draft(conversation_id: str):
        return _CHAT_DRAFTS.get(conversation_id)

    import app.api.routes.health as health_routes
    import app.core.token_service as token_service
    import app.modules.chat.service as chat_service
    import app.modules.constraint_builder.service as constraint_service
    import app.modules.datastores.interaction_rules_postgres as interaction_rules_postgres
    import app.modules.datastores.postgres as postgres_module
    import app.modules.datastores.service as datastore_service
    import app.modules.datastores.users as users_module

    _clear_graphrag_caches(graphrag_service)
    graphrag_service.load_published_chunks = lambda: list(chunks)
    graphrag_service.load_staging_chunks = lambda: list(chunks)
    graphrag_service.load_chunks = lambda: list(chunks)
    graphrag_service.load_published_relationships = lambda: list(relationships)
    graphrag_service.load_staging_relationships = lambda: list(relationships)
    graphrag_service.load_relationships = lambda: list(relationships)

    postgres_module.read_approved_constraint_rules = lambda: rules
    interaction_rules_postgres.read_approved_interaction_rules = lambda: []
    constraint_service.read_approved_constraint_rules = lambda: rules
    datastore_service.datastore_status = fake_datastore_status
    health_routes.datastore_status = fake_datastore_status
    users_module.get_user_by_id = fake_get_user_by_id
    token_service.get_user_by_id = fake_get_user_by_id

    for target in (postgres_module, chat_service):
        target.append_chat_message = append_chat_message
        target.upsert_patient_draft = upsert_patient_draft
        target.read_patient_draft = read_patient_draft
        target.read_chat_messages = read_chat_messages
        target.write_audit_event = lambda *_args, **_kwargs: None


_patch_session_dependencies()


@pytest.fixture(scope="session", autouse=True)
def _fast_test_environment() -> None:
    _mark_bootstrap_complete()


@pytest.fixture(autouse=True)
def _configure_test_auth(monkeypatch) -> None:
    monkeypatch.setattr(settings, "api_keys", TEST_API_KEY)
    monkeypatch.setattr(settings, "environment", "test")
    _patch_session_dependencies()


@pytest.fixture(autouse=True)
def _stub_clinical_intake_llm(request, monkeypatch) -> None:
    if "test_clinical_intake_extraction.py" in str(request.fspath):
        return
    if "test_clinical_intake_semantic.py" in str(request.fspath):
        return
    if "test_clinical_intake_selective.py" in str(request.fspath):
        return
    monkeypatch.setattr(
        "app.modules.clinical_intake_extraction.service._call_llm_extractor",
        lambda message: None,
    )


@pytest.fixture(autouse=True)
def _reset_constraint_cache() -> None:
    _CHAT_MESSAGES.clear()
    _CHAT_DRAFTS.clear()
    invalidate_constraint_cache()
    invalidate_interaction_rules_cache()
    yield
    _CHAT_MESSAGES.clear()
    _CHAT_DRAFTS.clear()
    invalidate_constraint_cache()
    invalidate_interaction_rules_cache()


@pytest.fixture(autouse=True)
def _isolate_session_clients(client, unauthenticated_client) -> None:
    client.cookies.clear()
    unauthenticated_client.cookies.clear()


@pytest.fixture(scope="session")
def client() -> TestClient:
    with TestClient(app, headers={settings.api_key_header: TEST_API_KEY}) as test_client:
        yield test_client


@pytest.fixture(scope="session")
def unauthenticated_client() -> TestClient:
    with TestClient(app) as test_client:
        yield test_client
