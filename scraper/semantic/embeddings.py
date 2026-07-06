"""Ollama embedding helpers for ingestion-time semantic steps."""

from __future__ import annotations

import logging
import math
from functools import lru_cache
from typing import Sequence

import httpx

from scraper.semantic import config

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


def _ollama_embeddings_url() -> str:
    return f"{config.EMBEDDING_BASE_URL.rstrip('/')}/api/embeddings"


def embed_texts(texts: list[str], *, timeout: float | None = None) -> list[list[float]]:
    if not texts:
        return []

    timeout = timeout or config.LLM_TIMEOUT_SECONDS
    vectors: list[list[float]] = []
    batch_size = max(1, config.EMBEDDING_BATCH_SIZE)

    try:
        with httpx.Client(timeout=timeout) as client:
            for start in range(0, len(texts), batch_size):
                batch = texts[start : start + batch_size]
                for text in batch:
                    response = client.post(
                        _ollama_embeddings_url(),
                        json={"model": config.EMBEDDING_MODEL, "prompt": text},
                    )
                    response.raise_for_status()
                    payload = response.json()
                    embedding = payload.get("embedding")
                    if not isinstance(embedding, list):
                        raise ValueError("Ollama embeddings response missing embedding vector")
                    vectors.append([float(value) for value in embedding])
    except Exception as exc:
        logger.warning("Embedding request failed: %s", exc)
        raise

    return vectors


def embeddings_available() -> bool:
    try:
        sample = embed_texts(["clinical guideline recommendation"], timeout=10.0)
        return bool(sample and sample[0])
    except Exception:
        return False


def max_similarity_vector_to_prototypes(
    text_vector: Sequence[float],
    prototypes: Sequence[str],
) -> float:
    if not text_vector or not prototypes:
        return 0.0
    prototype_vectors = _prototype_vectors(tuple(prototypes))
    return max(cosine_similarity(text_vector, prototype_vector) for prototype_vector in prototype_vectors)


@lru_cache(maxsize=2048)
def _embed_text_cached(text: str) -> tuple[float, ...]:
    if not text.strip():
        return tuple()
    return tuple(embed_texts([text])[0])


def embed_text(text: str) -> list[float]:
    return list(_embed_text_cached(text))


def max_similarity_to_prototypes(text: str, prototypes: Sequence[str]) -> float:
    if not text.strip() or not prototypes:
        return 0.0
    return max_similarity_vector_to_prototypes(_embed_text_cached(text), prototypes)


@lru_cache(maxsize=256)
def _prototype_vectors(prototypes: tuple[str, ...]) -> tuple[tuple[float, ...], ...]:
    vectors = embed_texts(list(prototypes))
    return tuple(tuple(vector) for vector in vectors)


def warmup_prototype_vectors(*prototype_maps: dict[str, list[str]]) -> None:
    """Pre-embed topic prototypes once per pipeline run."""
    for prototype_map in prototype_maps:
        for prototypes in prototype_map.values():
            _prototype_vectors(tuple(prototypes))
