import asyncio
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError

import pytest

from app.core.circuit_breaker import CircuitOpenError, get_circuit_breaker, reset_circuit_breakers
from app.core.config import settings
from app.core.governance_db import load_with_governance_guard
from app.core.rule_cache import RuleCache
from app.modules.constraint_builder import service as constraint_service
from app.modules.graphrag.evidence_scope import (
    EvidenceScope,
    merge_evidence_scopes,
    resolve_evidence_scope_from_chunk_ids,
)
from app.modules.graphrag.service import build_graphrag_context_async
from app.schemas.graphrag import GraphRAGContextRequest
from app.schemas.patient import PatientProfile


def test_circuit_breaker_opens_after_failures(monkeypatch) -> None:
    reset_circuit_breakers()
    monkeypatch.setattr(settings, "governance_circuit_failure_threshold", 2)
    monkeypatch.setattr(settings, "governance_circuit_recovery_seconds", 60.0)

    breaker = get_circuit_breaker("test_catalog")

    def fail() -> None:
        raise RuntimeError("db down")

    with pytest.raises(RuntimeError):
        breaker.call(fail)
    with pytest.raises(RuntimeError):
        breaker.call(fail)
    with pytest.raises(CircuitOpenError):
        breaker.call(fail)


def test_load_with_governance_guard_times_out(monkeypatch) -> None:
    reset_circuit_breakers()
    monkeypatch.setattr(settings, "governance_circuit_breaker_enabled", True)
    monkeypatch.setattr(settings, "governance_db_timeout_seconds", 0.01)

    def slow_loader() -> list[dict]:
        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(lambda: __import__("time").sleep(0.2) or [{"id": 1}])
            return future.result()

    with pytest.raises(TimeoutError):
        load_with_governance_guard("slow_catalog", slow_loader)


def test_rule_cache_serves_stale_when_circuit_open(monkeypatch) -> None:
    reset_circuit_breakers()
    monkeypatch.setattr(settings, "governance_circuit_breaker_enabled", True)
    monkeypatch.setattr(settings, "governance_circuit_failure_threshold", 1)

    cache = RuleCache(
        catalog_name="test_rules",
        ttl_seconds_setting="gdmt_policy_cache_ttl_seconds",
        list_key="rules",
        db_loader=lambda: (_ for _ in ()).throw(RuntimeError("postgres unavailable")),
        default_version="v1",
        postgres_source="postgres_test",
        fallback_path=None,
    )
    cache._cached_bundle = {"version": "stale", "source": "memory", "rules": [{"rule_id": "r1"}]}

    bundle = cache.load_bundle()
    assert bundle["source"] == "memory"
    assert bundle["rules"][0]["rule_id"] == "r1"


def test_constraint_rules_use_circuit_guard_on_timeout(monkeypatch) -> None:
    reset_circuit_breakers()
    constraint_service.invalidate_constraint_cache()
    monkeypatch.setattr(settings, "governance_circuit_breaker_enabled", True)
    monkeypatch.setattr(settings, "governance_db_timeout_seconds", 0.01)

    def slow_read() -> list[dict]:
        __import__("time").sleep(0.2)
        return [{"constraint_id": "c1", "action": "avoid", "metadata": {"constraint_type": "hard"}}]

    monkeypatch.setattr(constraint_service, "read_approved_constraint_rules", slow_read)

    rules = constraint_service.load_constraint_rules()
    assert rules
    assert rules[0]["metadata"]["fallback_source"] == "constraints_v1.json"


def test_resolve_evidence_scope_from_chunk_ids_expands_document_scope(monkeypatch, tmp_path) -> None:
    chunks_path = tmp_path / "chunks.jsonl"
    chunks_path.write_text(
        '{"chunk_id":"doc__renal__0001__abc","document_id":"spironolactone_label","section_id":"renal_sec","text":"Avoid when eGFR below 30."}\n',
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "app.modules.graphrag.evidence_scope.CHUNKS_PATH",
        chunks_path,
        raising=False,
    )
    monkeypatch.setattr(
        "app.modules.graphrag.evidence_scope._load_chunk_index",
        lambda: {
            "doc__renal__0001__abc": {
                "chunk_id": "doc__renal__0001__abc",
                "document_id": "spironolactone_label",
                "section_id": "renal_sec",
                "text": "Avoid when eGFR below 30.",
                "metadata": {"section_id": "renal_sec"},
            }
        },
    )

    scope = resolve_evidence_scope_from_chunk_ids(["doc__renal__0001__abc"])
    assert "doc__renal__0001__abc" in scope.chunk_ids
    assert "spironolactone_label" in scope.document_ids
    assert "renal_sec" in scope.section_ids


def test_graphrag_merges_constraint_scope(monkeypatch) -> None:
    monkeypatch.setattr(settings, "retrieval_backend", "databases")
    monkeypatch.setattr(settings, "graphrag_graph_guided_filter_enabled", True)
    monkeypatch.setattr(settings, "graphrag_multi_query_enabled", False)
    monkeypatch.setattr(settings, "hyde_retrieval_enabled", False)

    captured: dict[str, object] = {}

    def fake_scope(terms, *, top_k=24, chunk_ids=None):
        captured["chunk_ids"] = chunk_ids
        return EvidenceScope(
            chunk_ids=tuple(chunk_ids or []),
            document_ids=("kdigo_2024_ckd_guideline",),
        )

    def fake_chroma(query, top_k, *, scope=None):
        captured["scope"] = scope
        return []

    monkeypatch.setattr("app.modules.graphrag.service.resolve_evidence_scope", fake_scope)
    monkeypatch.setattr("app.modules.graphrag.service.retrieve_chroma", fake_chroma)
    monkeypatch.setattr("app.modules.graphrag.service.retrieve_neo4j", lambda *_args, **_kwargs: [])
    monkeypatch.setattr("app.modules.graphrag.service.retrieve_graph_facts", lambda *_args, **_kwargs: [])
    monkeypatch.setattr("app.modules.graphrag.service.retrieve_evidence_chunks", lambda *_args, **_kwargs: [])

    response = asyncio.run(
        build_graphrag_context_async(
            GraphRAGContextRequest(
                patient=PatientProfile(case_id="CASE_CONSTRAINT"),
                query="mra hyperkalemia",
                top_k=4,
                constraint_chunk_ids=["doc__renal__0001__abc"],
            )
        )
    )

    assert captured["chunk_ids"] == ["doc__renal__0001__abc"]
    assert "constraint_scope" in response.retrieval_sources
