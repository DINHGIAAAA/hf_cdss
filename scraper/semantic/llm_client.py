"""Sync Ollama chat-completions client for structured ingestion extraction."""

from __future__ import annotations

import hashlib
import json
import logging
import re
from pathlib import Path
from typing import Any

import httpx

from scraper.semantic import config

logger = logging.getLogger(__name__)


def extract_json_object(text: str) -> dict[str, Any] | None:
    stripped = (text or "").strip()
    if not stripped:
        return None
    try:
        data = json.loads(stripped)
        return data if isinstance(data, dict) else None
    except json.JSONDecodeError:
        pass
    match = re.search(r"\{.*\}", stripped, flags=re.DOTALL)
    if not match:
        return None
    try:
        data = json.loads(match.group(0))
        return data if isinstance(data, dict) else None
    except json.JSONDecodeError:
        return None


def llm_available() -> bool:
    try:
        with httpx.Client(timeout=10.0) as client:
            response = client.get(f"{config.LLM_BASE_URL.rstrip('/v1')}/api/tags")
            response.raise_for_status()
            return True
    except Exception:
        return False


def _cache_dir() -> Path | None:
    if not config.INGESTION_LLM_CACHE_ENABLED:
        return None
    path = Path(config.INGESTION_LLM_CACHE_DIR)
    path.mkdir(parents=True, exist_ok=True)
    return path


def _cache_key(system_prompt: str, user_prompt: str, *, max_tokens: int, model: str) -> str:
    raw = f"{model}|{max_tokens}|{system_prompt}|||{user_prompt}"
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()


def _read_cache(key: str) -> dict[str, Any] | None:
    cache_root = _cache_dir()
    if cache_root is None or not config.INGESTION_LLM_CACHE_ENABLED:
        return None
    cache_file = cache_root / f"{key}.json"
    if not cache_file.exists():
        return None
    try:
        payload = json.loads(cache_file.read_text(encoding="utf-8"))
        return payload if isinstance(payload, dict) else None
    except (OSError, json.JSONDecodeError):
        return None


def _write_cache(key: str, payload: dict[str, Any]) -> None:
    cache_root = _cache_dir()
    if cache_root is None or not config.INGESTION_LLM_CACHE_ENABLED:
        return
    cache_file = cache_root / f"{key}.json"
    cache_file.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def _call_llm_json_raw(system_prompt: str, user_prompt: str, *, max_tokens: int) -> dict[str, Any] | None:
    url = f"{config.LLM_BASE_URL.rstrip('/')}/chat/completions"
    payload = {
        "model": config.INGESTION_LLM_MODEL,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": 0,
        "max_tokens": max_tokens,
    }
    max_attempts = max(1, config.LLM_MAX_RETRIES + 1)

    for attempt in range(1, max_attempts + 1):
        try:
            with httpx.Client(timeout=config.LLM_TIMEOUT_SECONDS) as client:
                response = client.post(
                    url,
                    headers={"Content-Type": "application/json"},
                    json=payload,
                )
                response.raise_for_status()
                choices = response.json().get("choices", [])
                content = choices[0].get("message", {}).get("content", "") if choices else ""
            return extract_json_object(content)
        except Exception as exc:
            retryable = isinstance(exc, httpx.TimeoutException) or "timed out" in str(exc).lower()
            if retryable and attempt < max_attempts:
                logger.warning(
                    "LLM request timed out (attempt %s/%s, model=%s); retrying",
                    attempt,
                    max_attempts,
                    config.INGESTION_LLM_MODEL,
                )
                continue
            logger.warning("LLM request failed: %s", exc)
            return None

    return None


def call_llm_json(system_prompt: str, user_prompt: str, *, max_tokens: int | None = None) -> dict[str, Any] | None:
    max_tokens = max_tokens or config.LLM_MAX_TOKENS
    model = config.INGESTION_LLM_MODEL
    cache_key = _cache_key(system_prompt, user_prompt, max_tokens=max_tokens, model=model)
    cached = _read_cache(cache_key)
    if cached is not None:
        return cached

    payload = _call_llm_json_raw(system_prompt, user_prompt, max_tokens=max_tokens)
    if payload:
        _write_cache(cache_key, payload)
    return payload
