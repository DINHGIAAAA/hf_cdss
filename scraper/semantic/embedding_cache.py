"""Persistent on-disk cache for ingestion-time embedding vectors (SQLite-backed)."""

from __future__ import annotations

import hashlib
import json
import logging
import sqlite3
import threading
from pathlib import Path

from scraper.semantic import config

logger = logging.getLogger(__name__)

_lock = threading.Lock()
_conn: sqlite3.Connection | None = None


def cache_key(text: str) -> str:
    payload = f"{config.EMBEDDING_MODEL}|{text}"
    return hashlib.sha1(payload.encode("utf-8")).hexdigest()


def _db_path() -> Path | None:
    if not config.EMBEDDING_CACHE_ENABLED:
        return None
    from scraper.paths import data_root

    raw = (config.EMBEDDING_CACHE_DIR or "").strip()
    path = Path(raw) if raw else data_root() / ".cache" / "embeddings"
    path.mkdir(parents=True, exist_ok=True)
    return path / "embeddings.db"


def _connection() -> sqlite3.Connection | None:
    global _conn
    db_file = _db_path()
    if db_file is None:
        return None
    with _lock:
        if _conn is None:
            conn = sqlite3.connect(str(db_file), check_same_thread=False)
            conn.execute(
                "CREATE TABLE IF NOT EXISTS vectors ("
                "key TEXT PRIMARY KEY, model TEXT NOT NULL, vector TEXT NOT NULL)"
            )
            # WAL mode improves concurrent read/write performance
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA synchronous=NORMAL")
            conn.execute("PRAGMA cache_size=-64000")  # 64MB cache
            conn.commit()
            _conn = conn
    return _conn


def _import_legacy_json(key: str) -> list[float] | None:
    db_file = _db_path()
    if db_file is None:
        return None
    legacy_file = db_file.parent / f"{key}.json"
    if not legacy_file.exists():
        return None
    try:
        payload = json.loads(legacy_file.read_text(encoding="utf-8"))
        if payload.get("model") != config.EMBEDDING_MODEL:
            return None
        vector = payload.get("vector")
        if not isinstance(vector, list):
            return None
        parsed = [float(value) for value in vector]
        write_vector_from_key(key, parsed)
        return parsed
    except (OSError, json.JSONDecodeError, TypeError, ValueError):
        return None


def write_vector_from_key(key: str, vector: list[float]) -> None:
    conn = _connection()
    if conn is None or not vector:
        return
    with _lock:
        conn.execute(
            "INSERT OR REPLACE INTO vectors(key, model, vector) VALUES (?, ?, ?)",
            (key, config.EMBEDDING_MODEL, json.dumps(vector)),
        )
        conn.commit()


def read_vector(text: str) -> list[float] | None:
    if not text.strip():
        return None
    conn = _connection()
    key = cache_key(text)
    if conn is not None:
        with _lock:
            row = conn.execute(
                "SELECT vector, model FROM vectors WHERE key = ?",
                (key,),
            ).fetchone()
        if row is not None:
            vector_json, stored_model = row
            if stored_model == config.EMBEDDING_MODEL:
                try:
                    vector = json.loads(vector_json)
                    if isinstance(vector, list):
                        return [float(value) for value in vector]
                except (TypeError, ValueError, json.JSONDecodeError):
                    pass
    return _import_legacy_json(key)


def write_vector(text: str, vector: list[float]) -> None:
    if not text.strip() or not vector:
        return
    write_vector_from_key(cache_key(text), vector)


def _lookup_keys(keys: list[str]) -> dict[str, list[float]]:
    conn = _connection()
    if conn is None or not keys:
        return {}

    found: dict[str, list[float]] = {}
    chunk_size = 500
    for start in range(0, len(keys), chunk_size):
        chunk = keys[start : start + chunk_size]
        placeholders = ",".join("?" * len(chunk))
        with _lock:
            rows = conn.execute(
                f"SELECT key, vector, model FROM vectors WHERE key IN ({placeholders})",
                chunk,
            ).fetchall()
        for key, vector_json, model in rows:
            if model != config.EMBEDDING_MODEL:
                continue
            try:
                vector = json.loads(vector_json)
                if isinstance(vector, list):
                    found[key] = [float(value) for value in vector]
            except (TypeError, ValueError, json.JSONDecodeError):
                continue
    return found


def partition_cached(texts: list[str]) -> tuple[list[tuple[int, str]], dict[int, list[float]]]:
    """Return (missing indexed texts, cached vectors by original index).

    Duplicate texts in one batch share a cache key; every original index that hits
    must receive the vector (not only the last occurrence).
    """
    if not texts:
        return [], {}

    keys = [cache_key(text) for text in texts]
    cached_vectors = _lookup_keys(list(dict.fromkeys(keys)))

    cached: dict[int, list[float]] = {}
    missing: list[tuple[int, str]] = []
    for index, text in enumerate(texts):
        key = keys[index]
        vector = cached_vectors.get(key)
        if vector is not None:
            cached[index] = vector
            continue
        legacy = _import_legacy_json(key)
        if legacy is not None:
            cached[index] = legacy
            continue
        missing.append((index, text))

    if cached:
        logger.debug("Embedding cache hit: %s/%s texts", len(cached), len(texts))
    return missing, cached


def reset_connection_for_tests() -> None:
    global _conn
    with _lock:
        if _conn is not None:
            _conn.close()
            _conn = None
