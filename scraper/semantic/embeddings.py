"""Ollama embedding helpers for ingestion-time semantic steps.

Cache layers (outer → inner):
1. ``embed_text`` — in-process LRU for repeated strings within one pipeline run.
2. ``embed_texts`` — SQLite disk cache (cross-run) then Ollama HTTP.
"""

from __future__ import annotations

import logging
import math
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from functools import lru_cache
from typing import Sequence

import httpx

from scraper.semantic import config
from scraper.semantic.embedding_cache import partition_cached, write_vector

logger = logging.getLogger(__name__)


def cosine_similarity(left: Sequence[float], right: Sequence[float]) -> float:
    if not left or not right or len(left) != len(right):
        return 0.0
    dot = sum(a * b for a, b in zip(left, right))
    left_norm = math.sqrt(sum(a * a for a in left))
    right_norm = math.sqrt(sum(b * b for b in right))
    if left_norm == 0.0 or right_norm == 0.0:
        return 0.0
    return dot / (left_norm * right_norm)


def _ollama_base_url() -> str:
    return config.EMBEDDING_BASE_URL.rstrip("/")


def _ollama_embed_url() -> str:
    return f"{_ollama_base_url()}/api/embed"


def _ollama_embeddings_url() -> str:
    return f"{_ollama_base_url()}/api/embeddings"


def _parse_embedding_vectors(payload: dict) -> list[list[float]]:
    embeddings = payload.get("embeddings")
    if isinstance(embeddings, list) and embeddings:
        return [[float(value) for value in vector] for vector in embeddings]

    embedding = payload.get("embedding")
    if isinstance(embedding, list):
        return [[float(value) for value in embedding]]

    raise ValueError("Ollama embed response missing embedding vector(s)")


def _is_retryable_embed_error(exc: BaseException) -> bool:
    return isinstance(
        exc,
        (
            httpx.TimeoutException,
            httpx.NetworkError,
            httpx.RemoteProtocolError,
            ConnectionError,
            TimeoutError,
        ),
    )


def _with_embed_retries(operation_name: str, call, *, timeout: float):
    attempts = max(1, config.EMBEDDING_MAX_RETRIES + 1)
    last_exc: BaseException | None = None
    for attempt in range(1, attempts + 1):
        try:
            return call()
        except Exception as exc:  # noqa: BLE001 — classify retryable below
            last_exc = exc
            if attempt >= attempts or not _is_retryable_embed_error(exc):
                raise
            sleep_s = min(8.0, 1.5 * attempt)
            logger.warning(
                "Ollama %s failed (attempt %s/%s, timeout=%ss): %s; retrying in %.1fs",
                operation_name,
                attempt,
                attempts,
                timeout,
                exc,
                sleep_s,
            )
            time.sleep(sleep_s)
    assert last_exc is not None
    raise last_exc


def _embed_batch_ollama(texts: list[str], timeout: float) -> list[list[float]]:
    """True batch embedding via Ollama /api/embed (input=list)."""

    def _call() -> list[list[float]]:
        with httpx.Client(timeout=timeout) as client:
            response = client.post(
                _ollama_embed_url(),
                json={
                    "model": config.EMBEDDING_MODEL,
                    "input": texts,
                    # Do not pin the embed model on GPU for hours — blocks chat LLMs.
                    "keep_alive": "0",
                },
            )
            response.raise_for_status()
            return _parse_embedding_vectors(response.json())

    return _with_embed_retries(f"/api/embed x{len(texts)}", _call, timeout=timeout)


def _embed_single_text(text: str, timeout: float) -> list[float]:
    """Legacy single-text embedding via /api/embeddings."""

    def _call() -> list[float]:
        with httpx.Client(timeout=timeout) as client:
            response = client.post(
                _ollama_embeddings_url(),
                json={
                    "model": config.EMBEDDING_MODEL,
                    "prompt": text,
                    "keep_alive": "0",
                },
            )
            response.raise_for_status()
            return _parse_embedding_vectors(response.json())[0]

    return _with_embed_retries("/api/embeddings", _call, timeout=timeout)


def _embed_texts_remote(texts: list[str], *, timeout: float, fail_fast: bool) -> list[list[float]]:
    if not texts:
        return []

    batch_size = max(1, config.EMBEDDING_BATCH_SIZE)

    if len(texts) == 1:
        try:
            return _embed_batch_ollama(texts, timeout)
        except Exception as batch_exc:
            # Prefer one fallback path; do not stack two full timeouts blindly.
            logger.debug("Ollama /api/embed single failed (%s); trying /api/embeddings", batch_exc)
            return [_embed_single_text(texts[0], timeout)]

    all_vectors: list[list[float] | None] = [None] * len(texts)
    errors: list[tuple[int, Exception]] = []

    def _store_batch(start: int, vectors: list[list[float]]) -> None:
        for offset, vector in enumerate(vectors):
            all_vectors[start + offset] = vector

    def _embed_batch_with_fallback(start: int, batch: list[str]) -> None:
        try:
            _store_batch(start, _embed_batch_ollama(batch, timeout))
            return
        except Exception as batch_exc:
            logger.debug("Ollama /api/embed batch failed (%s texts): %s", len(batch), batch_exc)

        max_workers = min(config.EMBEDDING_PARALLEL_WORKERS, len(batch))
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {
                executor.submit(_embed_single_text, text, timeout): start + offset
                for offset, text in enumerate(batch)
            }
            for future in as_completed(futures):
                idx = futures[future]
                try:
                    all_vectors[idx] = future.result()
                except Exception as exc:
                    errors.append((idx, exc))
                    if fail_fast:
                        raise RuntimeError(f"Embedding failed for text[{idx}]: {exc}") from exc

    for start in range(0, len(texts), batch_size):
        batch = texts[start : start + batch_size]
        _embed_batch_with_fallback(start, batch)

    if errors and not fail_fast:
        error_msgs = [f"text[{i}]: {exc}" for i, exc in errors]
        raise RuntimeError(f"Embedding failed for {len(errors)} texts: {'; '.join(error_msgs[:5])}")

    missing = [i for i, vec in enumerate(all_vectors) if vec is None]
    if missing:
        raise RuntimeError(f"Missing embeddings for indices: {missing}")

    return [vector for vector in all_vectors if vector is not None]  # type: ignore[misc]


def _embed_uncached_texts(
    indexed_texts: list[tuple[int, str]],
    *,
    timeout: float,
    fail_fast: bool,
) -> dict[int, list[float]]:
    if not indexed_texts:
        return {}

    texts = [text for _, text in indexed_texts]
    vectors = _embed_texts_remote(texts, timeout=timeout, fail_fast=fail_fast)
    result: dict[int, list[float]] = {}
    for (index, text), vector in zip(indexed_texts, vectors):
        write_vector(text, vector)
        result[index] = vector
    return result


def _truncate_embed_input(text: str) -> str:
    max_chars = max(512, config.EMBEDDING_MAX_INPUT_CHARS)
    if len(text) <= max_chars:
        return text
    return text[:max_chars]


def embed_texts(
    texts: list[str],
    *,
    timeout: float | None = None,
    fail_fast: bool = True,
    use_cache: bool = True,
) -> list[list[float]]:
    """Embed texts using Ollama /api/embed batches, with parallel /api/embeddings fallback.

    Args:
        texts: List of texts to embed
        timeout: Request timeout in seconds
        fail_fast: If True, raise exception on first failure. If False, collect all errors.
        use_cache: When True, read/write persistent embedding cache entries.
    """
    if not texts:
        return []

    texts = [_truncate_embed_input(text) for text in texts]
    timeout = timeout if timeout is not None else config.EMBEDDING_TIMEOUT_SECONDS
    resolved: dict[int, list[float]] = {}
    missing_indexed: list[tuple[int, str]] = [(index, text) for index, text in enumerate(texts)]

    if use_cache and config.EMBEDDING_CACHE_ENABLED:
        missing_indexed, cached = partition_cached(texts)
        resolved.update(cached)
        if cached:
            logger.debug("Embedding cache hit: %s/%s texts", len(cached), len(texts))

    if missing_indexed:
        fetched = _embed_uncached_texts(missing_indexed, timeout=timeout, fail_fast=fail_fast)
        resolved.update(fetched)

    missing_resolved = [index for index in range(len(texts)) if index not in resolved]
    if missing_resolved:
        raise KeyError(
            f"Missing embedding vectors for indices {missing_resolved[:8]} "
            f"(batch size={len(texts)}, cached/fetched={len(resolved)})"
        )
    return [resolved[index] for index in range(len(texts))]


def embeddings_available() -> bool:
    """Check if Ollama embeddings are available. Fails if embedding service is down."""
    sample = embed_texts(
        ["clinical guideline recommendation"],
        timeout=min(30.0, config.EMBEDDING_TIMEOUT_SECONDS),
    )
    return bool(sample and sample[0])


def max_similarity_vector_to_prototypes(
    text_vector: Sequence[float],
    prototypes: Sequence[str],
) -> float:
    if not text_vector or not prototypes:
        return 0.0
    prototype_vectors = _prototype_vectors(tuple(prototypes))
    return max(cosine_similarity(text_vector, prototype_vector) for prototype_vector in prototype_vectors)


@lru_cache(maxsize=8192)
def _in_process_embedding(text: str) -> tuple[float, ...]:
    """Memoize single-text embeddings for the current process (delegates to embed_texts)."""
    if not text:
        return tuple()
    return tuple(embed_texts([text])[0])


def embed_text(text: str) -> list[float]:
    """Embed one text: LRU (this run) → SQLite (disk) → Ollama."""
    return list(_in_process_embedding(text.strip()))


def clear_embedding_caches() -> None:
    """Clear in-process embedding memoization (for tests and pipeline restarts)."""
    _in_process_embedding.cache_clear()
    _prototype_vectors.cache_clear()


def max_similarity_to_prototypes(text: str, prototypes: Sequence[str]) -> float:
    if not text.strip() or not prototypes:
        return 0.0
    return max_similarity_vector_to_prototypes(embed_text(text), prototypes)


@lru_cache(maxsize=256)
def _prototype_vectors(prototypes: tuple[str, ...]) -> tuple[tuple[float, ...], ...]:
    vectors = embed_texts(list(prototypes))
    return tuple(tuple(vector) for vector in vectors)


def warmup_prototype_vectors(*prototype_maps: dict[str, list[str]]) -> None:
    """Pre-embed topic prototypes once per pipeline run."""
    for prototype_map in prototype_maps:
        for prototypes in prototype_map.values():
            _prototype_vectors(tuple(prototypes))
