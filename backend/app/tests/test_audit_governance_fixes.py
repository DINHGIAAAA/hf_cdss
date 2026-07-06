import threading

from app.core.config import settings
from app.core.middleware import _is_admin_rate_limited
from app.modules.clinical_intake_extraction import semantic
from app.modules.governance.bulk_approve import bulk_approve_constraint_rules
from starlette.requests import Request


def test_catalog_cache_uses_lock_for_concurrent_build(monkeypatch) -> None:
    semantic.clear_catalog_cache()
    calls = {"count": 0}

    def fake_embed(texts: list[str]) -> list[list[float]]:
        calls["count"] += 1
        return [[float(len(text))] for text in texts]

    monkeypatch.setattr(semantic, "embed_documents", fake_embed)

    results: list[int] = []

    def worker() -> None:
        entries, _ = semantic._catalog_vectors()
        results.append(len(entries))

    threads = [threading.Thread(target=worker) for _ in range(4)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert calls["count"] == 1
    assert len(results) == 4
    assert all(count > 0 for count in results)


def test_admin_rate_limit_blocks_after_threshold(monkeypatch) -> None:
    monkeypatch.setattr(settings, "admin_rate_limit_requests", 2)
    monkeypatch.setattr(settings, "admin_rate_limit_window_seconds", 60)

    scope = {
        "type": "http",
        "method": "GET",
        "path": "/api/v1/admin/constraints",
        "headers": [(b"x-api-key", b"admin-test")],
        "client": ("127.0.0.1", 1234),
    }
    request = Request(scope)

    assert _is_admin_rate_limited(request) is False
    assert _is_admin_rate_limited(request) is False
    assert _is_admin_rate_limited(request) is True


def test_bulk_approve_constraint_rules_dry_run(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.modules.governance.bulk_approve.list_draft_constraint_rule_ids",
        lambda **_kwargs: [11, 12],
    )
    monkeypatch.setattr(
        "app.modules.governance.bulk_approve.approve_constraint_rule",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("should not approve")),
    )

    result = bulk_approve_constraint_rules("admin-1", dry_run=True)

    assert result["dry_run"] is True
    assert result["candidate_ids"] == [11, 12]
    assert result["approved"] == []


def test_preload_runtime_caches_is_invoked_from_bootstrap(monkeypatch) -> None:
    from app.modules.datastores import service as datastore_service

    called = {"preload": False}

    def fake_preload() -> dict[str, object]:
        called["preload"] = True
        return {"constraints": {"status": "ok", "count": 3}}

    monkeypatch.setattr(datastore_service, "sync_artifacts_from_processed_bucket", lambda *_args, **_kwargs: {"status": "ok"})
    monkeypatch.setattr(datastore_service, "initialize_postgres", lambda: {"status": "ok"})
    monkeypatch.setattr(datastore_service, "initialize_chroma", lambda: {"status": "ok"})
    monkeypatch.setattr(datastore_service, "initialize_neo4j", lambda: {"status": "ok"})
    monkeypatch.setattr(datastore_service, "_preload_runtime_caches", fake_preload)

    original_import = __import__

    def fake_import(name, *args, **kwargs):
        if name == "app.modules.datastores.seed_governance_catalogs":
            class _SeedModule:
                @staticmethod
                def seed_all_governance_catalogs() -> dict[str, object]:
                    return {"constraints": {"inserted": 1}}

            return _SeedModule
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr("builtins.__import__", fake_import)

    results = datastore_service.bootstrap_datastores()

    assert called["preload"] is True
    assert "governance_seed" in results
    assert results["runtime_caches"]["constraints"]["count"] == 3
