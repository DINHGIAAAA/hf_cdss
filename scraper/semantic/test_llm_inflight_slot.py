"""Tests for LLM in-flight slot limiter."""

from __future__ import annotations

import threading
import time

from scraper.semantic import llm_client


def test_llm_inflight_slot_limits_concurrent_holders_same_model(monkeypatch):
    monkeypatch.setattr(llm_client.config, "LLM_CONCURRENCY", 1)
    monkeypatch.setattr(llm_client.config, "LLM_SLOTS_PER_MODEL", True)
    monkeypatch.setattr(llm_client, "fcntl", None)
    with llm_client._thread_slots_lock:
        llm_client._thread_slots.clear()

    active = 0
    max_active = 0
    lock = threading.Lock()

    def worker() -> None:
        nonlocal active, max_active
        with llm_client._llm_inflight_slot("qwen2.5:1.5b"):
            with lock:
                active += 1
                max_active = max(max_active, active)
            time.sleep(0.05)
            with lock:
                active -= 1

    threads = [threading.Thread(target=worker) for _ in range(4)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=5)

    assert max_active == 1


def test_llm_inflight_slot_different_models_do_not_block(monkeypatch):
    monkeypatch.setattr(llm_client.config, "LLM_CONCURRENCY", 1)
    monkeypatch.setattr(llm_client.config, "LLM_SLOTS_PER_MODEL", True)
    monkeypatch.setattr(llm_client, "fcntl", None)
    with llm_client._thread_slots_lock:
        llm_client._thread_slots.clear()

    gate = threading.Event()
    both_inside = threading.Event()
    inside = 0
    lock = threading.Lock()

    def worker(model: str) -> None:
        nonlocal inside
        with llm_client._llm_inflight_slot(model):
            with lock:
                inside += 1
                if inside >= 2:
                    both_inside.set()
            gate.wait(timeout=2)
            with lock:
                inside -= 1

    threads = [
        threading.Thread(target=worker, args=("qwen2.5:1.5b",)),
        threading.Thread(target=worker, args=("qwen2.5:7b",)),
    ]
    for thread in threads:
        thread.start()
    assert both_inside.wait(timeout=2), "different models should hold slots concurrently"
    gate.set()
    for thread in threads:
        thread.join(timeout=5)
