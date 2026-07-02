"""Sync Ollama chat-completions client for structured ingestion extraction."""

from __future__ import annotations

import json
import logging
import re
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


def call_llm_json(system_prompt: str, user_prompt: str, *, max_tokens: int | None = None) -> dict[str, Any] | None:
    max_tokens = max_tokens or config.LLM_MAX_TOKENS
    try:
        with httpx.Client(timeout=config.LLM_TIMEOUT_SECONDS) as client:
            response = client.post(
                f"{config.LLM_BASE_URL.rstrip('/')}/chat/completions",
                headers={"Content-Type": "application/json"},
                json={
                    "model": config.LLM_MODEL,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    "temperature": 0,
                    "max_tokens": max_tokens,
                },
            )
            response.raise_for_status()
            choices = response.json().get("choices", [])
            content = choices[0].get("message", {}).get("content", "") if choices else ""
    except Exception as exc:
        logger.warning("LLM request failed: %s", exc)
        return None

    return extract_json_object(content)
