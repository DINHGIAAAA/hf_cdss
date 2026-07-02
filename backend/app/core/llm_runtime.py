"""Shared helpers for Ollama's OpenAI-compatible chat completions API."""

from __future__ import annotations

from app.core.config import settings


def chat_completions_url() -> str:
    return f"{settings.llm_base_url.rstrip('/')}/chat/completions"


def llm_auth_headers() -> dict[str, str]:
    headers = {"Content-Type": "application/json"}
    if settings.openai_api_key and "api.openai.com" in settings.llm_base_url:
        headers["Authorization"] = f"Bearer {settings.openai_api_key}"
    return headers


def llm_requires_api_key() -> bool:
    return bool("api.openai.com" in settings.llm_base_url and not settings.openai_api_key)


def llm_chat_completions_enabled() -> bool:
    return settings.llm_api_type.lower().strip() == "chat_completions" and not llm_requires_api_key()
