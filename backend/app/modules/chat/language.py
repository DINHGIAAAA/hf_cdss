"""Lightweight chat language detection from clinician message text."""

from __future__ import annotations

import re

_VI_DIACRITICS_RE = re.compile(
    r"[àáảãạăằắẳẵặâầấẩẫậèéẻẽẹêềếểễệìíỉĩịòóỏõọôồốổỗộơờớởỡợùúủũụưừứửữựỳýỷỹỵđ]",
    re.IGNORECASE,
)
_EN_QUESTION_RE = re.compile(
    r"\b(should|what|how|when|can|could|would|add|start|stop|patient|dose|recommend|about)\b",
    re.IGNORECASE,
)
_VI_HINT_RE = re.compile(
    r"\b(khong|không|nen|nên|thuoc|thuốc|benh nhan|bệnh nhân|lieu|liều|co nen|có nên|the nao|thế nào|"
    r"bat dau|bắt đầu|ngung|ngừng|tang|tăng|giam|giảm)\b",
    re.IGNORECASE,
)


def detect_message_language(message: str, *, fallback: str = "vi") -> str:
    """Infer vi/en from message content. Fast heuristic — no LLM."""
    text = (message or "").strip()
    if not text:
        return fallback

    if _VI_DIACRITICS_RE.search(text):
        return "vi"

    normalized = re.sub(r"\s+", " ", text.lower())
    if _VI_HINT_RE.search(normalized):
        return "vi"

    if _EN_QUESTION_RE.search(text):
        return "en"

    ascii_chars = sum(1 for char in text if ord(char) < 128)
    if len(text) > 0 and ascii_chars / len(text) >= 0.92:
        return "en"

    return fallback


def resolve_chat_language(message: str, requested: str | None) -> str:
    """Prefer detected message language; fall back to UI/request default."""
    base = (requested or "vi").lower().strip()
    if base not in {"vi", "en"}:
        base = "vi"
    detected = detect_message_language(message, fallback=base)
    return detected if detected in {"vi", "en"} else base
