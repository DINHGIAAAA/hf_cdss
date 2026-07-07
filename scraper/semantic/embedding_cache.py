"""Persistent on-disk cache for ingestion-time embedding vectors."""

from __future__ import annotations

import hashlib
import json
import logging
from pathlib import Path

from scraper.semantic import config

logger = logging.getLogger(__name__)


def _cache_root() -> Path | None:
    raw = config.EMBEDDING_CACHE_DIR.strip()
    if not raw or not config.EMBEDDING_CACHE_ENABLED:
        return None
    path = Path(raw)
    path.mkdir(parents=True, exist_ok=True)
    return path


def cache_key(text: str) -> str:
    payload = f"{config.EMBEDDING_MODEL}|{text}"
    return hashlib.sha1(payload.encode("utf-8")).hexdigest()


def read_vector(text: str) -> list[float] | None:
    root = _cache_root()
    if root is None or not text.strip():
        return None
    cache_file = root / f"{cache_key(text)}.json"
    if not cache_file.exists():
        return None
    try:
        payload = json.loads(cache_file.read_text(encoding="utf-8"))
        if payload.get("model") != config.EMBEDDING_MODEL:
            return None
        vector = payload.get("vector")
        if not isinstance(vector, list):
            return None
        return [float(value) for value in vector]
    except (OSError, json.JSONDecodeError, TypeError, ValueError):
        return None


def write_vector(text: str, vector: list[float]) -> None:
    root = _cache_root()
    if root is None or not text.strip() or not vector:
        return
    cache_file = root / f"{cache_key(text)}.json"
    payload = {"model": config.EMBEDDING_MODEL, "vector": vector}
    try:
        cache_file.write_text(json.dumps(payload), encoding="utf-8")
    except OSError as exc:
        logger.debug("Embedding cache write failed for %s: %s", cache_key(text), exc)


def partition_cached(texts: list[str]) -> tuple[list[tuple[int, str]], dict[int, list[float]]]:
    """Return (missing indexed texts, cached vectors by original index)."""
    missing: list[tuple[int, str]] = []
    cached: dict[int, list[float]] = {}
    for index, text in enumerate(texts):
        vector = read_vector(text)
        if vector is not None:
            cached[index] = vector
        else:
            missing.append((index, text))
    return missing, cached
