"""Runtime tuning for the semantic ingestion pipeline."""

from __future__ import annotations

import os

from scraper.models import EMBEDDING_MODEL, EXPLANATION_MODEL


def _env_float(key: str, default: float) -> float:
    raw = os.environ.get(key)
    if raw is None:
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def _env_int(key: str, default: int) -> int:
    raw = os.environ.get(key)
    if raw is None:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


LLM_BASE_URL = os.environ.get("HF_CDSS_LLM_BASE_URL", "http://localhost:11434/v1")
LLM_MODEL = os.environ.get("HF_CDSS_LLM_MODEL", EXPLANATION_MODEL)
LLM_TIMEOUT_SECONDS = _env_float("HF_CDSS_LLM_TIMEOUT_SECONDS", 120.0)
LLM_MAX_TOKENS = _env_int("HF_CDSS_INGESTION_LLM_MAX_TOKENS", 1800)

EMBEDDING_BASE_URL = os.environ.get("HF_CDSS_EMBEDDING_BASE_URL", "http://localhost:11434")
EMBEDDING_MODEL = os.environ.get("HF_CDSS_EMBEDDING_MODEL", EMBEDDING_MODEL)
EMBEDDING_BATCH_SIZE = _env_int("HF_CDSS_EMBEDDING_BATCH_SIZE", 16)

SECTION_SIMILARITY_THRESHOLD = _env_float("HF_CDSS_SECTION_SIMILARITY_THRESHOLD", 0.52)
SEMANTIC_CHUNK_BREAKPOINT_THRESHOLD = _env_float("HF_CDSS_SEMANTIC_CHUNK_BREAKPOINT", 0.42)
CLAIM_DEDUP_THRESHOLD = _env_float("HF_CDSS_CLAIM_DEDUP_THRESHOLD", 0.92)
CHUNK_DEDUP_THRESHOLD = _env_float("HF_CDSS_CHUNK_DEDUP_THRESHOLD", 0.95)

DEFAULT_CHUNK_SIZE = _env_int("HF_CDSS_CHUNK_SIZE", 500)
DEFAULT_CHUNK_OVERLAP = _env_int("HF_CDSS_CHUNK_OVERLAP", 75)
MAX_LLM_SECTION_CHARS = _env_int("HF_CDSS_MAX_LLM_SECTION_CHARS", 12000)
MAX_LLM_CLAIMS_PER_SECTION = _env_int("HF_CDSS_MAX_LLM_CLAIMS_PER_SECTION", 40)
