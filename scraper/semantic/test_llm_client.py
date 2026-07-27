"""Tests for call_llm_json routing logic (timeout, num_ctx, cache key)."""

from __future__ import annotations

from contextlib import contextmanager

import httpx

from scraper.semantic import config
from scraper.semantic import llm_client


@contextmanager
def _nullctx():
    yield


class _FakeClient:
    """Minimal stand-in for httpx.Client that records posted payloads."""

    def __init__(self, post_fn):
        self._post_fn = post_fn

    def __enter__(self):
        return self

    def __exit__(self, *a):
        pass

    def post(self, url, headers=None, json=None, timeout=None):
        self._post_fn(url, headers, json, timeout)
        raise httpx.PoolTimeout("no slot")


def test_timeout_routing_refine_model(monkeypatch):
    """When model == CONDITION_REFINE_LLM_MODEL, must use CONDITION_REFINE_LLM_TIMEOUT_SECONDS."""
    captured: dict = {}

    def fake_raw(_sp, _up, **kw):
        captured.update(kw)
        return None

    monkeypatch.setattr(llm_client, "_call_llm_json_raw", fake_raw)
    monkeypatch.setattr(llm_client, "_read_cache", lambda *a, **kw: None)
    monkeypatch.setattr(llm_client, "_write_cache", lambda *a, **kw: None)

    llm_client.call_llm_json(
        "sys",
        '{"drug":"a"}',
        max_tokens=100,
        model=config.CONDITION_REFINE_LLM_MODEL,
    )

    assert captured["timeout_seconds"] == config.CONDITION_REFINE_LLM_TIMEOUT_SECONDS


def test_timeout_routing_default_model(monkeypatch):
    """When model is unset, must use LLM_TIMEOUT_SECONDS (not INGESTION)."""
    captured: dict = {}

    def fake_raw(_sp, _up, **kw):
        captured.update(kw)
        return None

    monkeypatch.setattr(llm_client, "_call_llm_json_raw", fake_raw)
    monkeypatch.setattr(llm_client, "_read_cache", lambda *a, **kw: None)
    monkeypatch.setattr(llm_client, "_write_cache", lambda *a, **kw: None)

    llm_client.call_llm_json(
        "sys",
        '{"drug":"a"}',
        max_tokens=100,
        model=None,
    )

    assert captured["timeout_seconds"] == config.LLM_TIMEOUT_SECONDS


def test_timeout_routing_ingestion_model(monkeypatch):
    """When model == INGESTION_LLM_MODEL and differs from CONDITION_REFINE, must use LLM_TIMEOUT_SECONDS."""
    # INGESTION_LLM_MODEL and CONDITION_REFINE_LLM_MODEL both default to LLM_MODEL,
    # so the branch in call_llm_json cannot distinguish them by default.
    # Mock them to distinct values to exercise the routing correctly.
    monkeypatch.setattr(config, "INGESTION_LLM_MODEL", "ingestion-model")
    monkeypatch.setattr(config, "CONDITION_REFINE_LLM_MODEL", "refine-model")
    captured: dict = {}

    def fake_raw(_sp, _up, **kw):
        captured.update(kw)
        return None

    monkeypatch.setattr(llm_client, "_call_llm_json_raw", fake_raw)
    monkeypatch.setattr(llm_client, "_read_cache", lambda *a, **kw: None)
    monkeypatch.setattr(llm_client, "_write_cache", lambda *a, **kw: None)

    llm_client.call_llm_json(
        "sys",
        '{"drug":"a"}',
        max_tokens=100,
        model=config.INGESTION_LLM_MODEL,
    )

    assert captured["timeout_seconds"] == config.LLM_TIMEOUT_SECONDS


def test_timeout_explicit_override(monkeypatch):
    """Explicit timeout_seconds kwarg must win over all implicit routing."""
    captured: dict = {}

    def fake_raw(_sp, _up, **kw):
        captured.update(kw)
        return None

    monkeypatch.setattr(llm_client, "_call_llm_json_raw", fake_raw)
    monkeypatch.setattr(llm_client, "_read_cache", lambda *a, **kw: None)
    monkeypatch.setattr(llm_client, "_write_cache", lambda *a, **kw: None)

    llm_client.call_llm_json(
        "sys",
        '{"drug":"a"}',
        max_tokens=100,
        model=config.CONDITION_REFINE_LLM_MODEL,
        timeout_seconds=99.0,
    )

    assert captured["timeout_seconds"] == 99.0


def test_num_ctx_default(monkeypatch):
    """call_llm_json passes num_ctx=None to _call_llm_json_raw when caller omits it.

    Resolution (None → 32768) happens inside _call_llm_json_raw.
    """
    captured: dict = {}

    def fake_raw(_sp, _up, **kw):
        captured.update(kw)
        return None

    monkeypatch.setattr(llm_client, "_call_llm_json_raw", fake_raw)
    monkeypatch.setattr(llm_client, "_read_cache", lambda *a, **kw: None)
    monkeypatch.setattr(llm_client, "_write_cache", lambda *a, **kw: None)

    llm_client.call_llm_json("sys", '{"drug":"a"}', max_tokens=100)

    # num_ctx=None means "use internal default". _call_llm_json_raw resolves it
    # to 32768 (was 2048 before the fix — that silently truncated qwen2.5:7b's 32k context).
    assert captured["num_ctx"] is None


def test_num_ctx_resolved_inside_raw(monkeypatch):
    """_call_llm_json_raw must resolve num_ctx=None to 32768, not leave it at 2048."""
    captured_payload: dict = {}

    def fake_http_post(url, headers, json, timeout):
        captured_payload["payload"] = json
        raise httpx.PoolTimeout("no slot")

    monkeypatch.setattr(llm_client.httpx, "Client", lambda *a, **kw: _FakeClient(fake_http_post))
    monkeypatch.setattr(llm_client, "_llm_inflight_slot", lambda *a, **kw: _nullctx())

    result = llm_client._call_llm_json_raw("sys", '{"drug":"a"}', max_tokens=100)

    assert captured_payload["payload"]["options"]["num_ctx"] == 32768


def test_num_ctx_caller_override(monkeypatch):
    """Callers can override num_ctx; it must not be silently dropped."""
    captured: dict = {}

    def fake_raw(_sp, _up, **kw):
        captured.update(kw)
        return None

    monkeypatch.setattr(llm_client, "_call_llm_json_raw", fake_raw)
    monkeypatch.setattr(llm_client, "_read_cache", lambda *a, **kw: None)
    monkeypatch.setattr(llm_client, "_write_cache", lambda *a, **kw: None)

    llm_client.call_llm_json("sys", '{"drug":"a"}', max_tokens=100, num_ctx=8192)

    assert captured["num_ctx"] == 8192


def test_cache_key_includes_max_tokens(monkeypatch):
    """Cache key must vary with max_tokens so different budgets don't share entries."""
    captured_keys: list = []

    def fake_cache_read(key, **kw):
        return None

    def fake_cache_write(key, **kw):
        captured_keys.append(key)

    monkeypatch.setattr(llm_client, "_read_cache", fake_cache_read)
    monkeypatch.setattr(llm_client, "_write_cache", fake_cache_write)
    monkeypatch.setattr(llm_client, "_call_llm_json_raw", lambda _sp, _up, **kw: {"ok": True})

    key1 = llm_client._cache_key("sys", '{"drug":"a"}', max_tokens=100, model="test")
    key2 = llm_client._cache_key("sys", '{"drug":"a"}', max_tokens=250, model="test")

    assert key1 != key2, "Cache keys must differ when max_tokens differs"


def test_refine_with_tight_max_tokens_not_truncated(monkeypatch):
    """refine_rule_conditions_with_llm must still return usable conditions at max_tokens=250."""
    captured: dict = {}

    def fake_call_llm(_sp, _up, **kw):
        captured.update(kw)
        # Simulate: model respects max_tokens and returns structured output
        return {
            "conditions": {
                "egfr": "<30",
                "pregnancy": True,
                "decompensated_hf": True,
            },
            "confidence": 0.92,
            "rationale": "Clear clinical criteria from evidence",
        }

    monkeypatch.setattr(llm_client, "call_llm_json", fake_call_llm)
    monkeypatch.setattr(llm_client, "llm_available", lambda: True)

    result = llm_client.call_llm_json(
        "sys",
        '{"drug":"metoprolol","evidence":"Avoid in decompensated heart failure when patient requires inotropic support. eGFR < 30."}',
        max_tokens=250,
        model=config.CONDITION_REFINE_LLM_MODEL,
        cache_predicate=lambda p: bool(p.get("conditions")),
    )

    assert result is not None
    assert isinstance(result.get("conditions"), dict)
    assert len(result["conditions"]) >= 2, (
        f"With tight max_tokens=250, expected multi-condition dict; got {result.get('conditions')}"
    )
