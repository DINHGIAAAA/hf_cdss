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


def _resolved_cache_dir(env_key: str, subdir: str) -> str:
    raw = os.environ.get(env_key, "").strip()
    if raw:
        return raw
    from scraper.paths import data_root

    return str(data_root() / ".cache" / subdir)


LLM_BASE_URL = os.environ.get("HF_CDSS_LLM_BASE_URL", "http://localhost:11434/v1")
LLM_MODEL = os.environ.get("HF_CDSS_LLM_MODEL", EXPLANATION_MODEL)
INGESTION_LLM_MODEL = os.environ.get("HF_CDSS_INGESTION_LLM_MODEL", LLM_MODEL)
LLM_TIMEOUT_SECONDS = _env_float("HF_CDSS_LLM_TIMEOUT_SECONDS", 45.0)
# Claim extraction on CPU Ollama often needs longer than chat; keep a separate budget.
INGESTION_LLM_TIMEOUT_SECONDS = _env_float(
    "HF_CDSS_INGESTION_LLM_TIMEOUT_SECONDS",
    max(LLM_TIMEOUT_SECONDS, 300.0),
)
LLM_MAX_RETRIES = _env_int("HF_CDSS_LLM_MAX_RETRIES", 2)
LLM_MAX_TOKENS = _env_int("HF_CDSS_INGESTION_LLM_MAX_TOKENS", 900)
LLM_CONCURRENCY = _env_int("HF_CDSS_LLM_CONCURRENCY", 1)
INGESTION_LLM_CACHE_ENABLED = os.environ.get("HF_CDSS_INGESTION_LLM_CACHE_ENABLED", "true").lower() in {
    "1",
    "true",
    "yes",
}
INGESTION_LLM_CACHE_DIR = _resolved_cache_dir("HF_CDSS_INGESTION_LLM_CACHE_DIR", "llm_claims")
CLAIM_LLM_ENABLED = os.environ.get("HF_CDSS_CLAIM_LLM_ENABLED", "true").lower() in {"1", "true", "yes"}
CLAIM_LLM_MIN_PATTERN_MATCHES = _env_int("HF_CDSS_CLAIM_LLM_MIN_PATTERN_MATCHES", 3)

EMBEDDING_BASE_URL = os.environ.get("HF_CDSS_EMBEDDING_BASE_URL", "http://localhost:11434")
EMBEDDING_MODEL = os.environ.get("HF_CDSS_EMBEDDING_MODEL", EMBEDDING_MODEL)
EMBEDDING_BATCH_SIZE = _env_int("HF_CDSS_EMBEDDING_BATCH_SIZE", 16)
EMBEDDING_PARALLEL_WORKERS = _env_int("HF_CDSS_EMBEDDING_PARALLEL_WORKERS", 2)
EMBEDDING_CACHE_ENABLED = os.environ.get("HF_CDSS_EMBEDDING_CACHE_ENABLED", "true").lower() in {"1", "true", "yes"}
EMBEDDING_CACHE_DIR = _resolved_cache_dir("HF_CDSS_EMBEDDING_CACHE_DIR", "embeddings")
EMBEDDING_DEDUP_ENABLED = os.environ.get("HF_CDSS_EMBEDDING_DEDUP_ENABLED", "false").lower() in {"1", "true", "yes"}

SEMANTIC_CHUNK_ENABLED = os.environ.get("HF_CDSS_SEMANTIC_CHUNK_ENABLED", "true").lower() in {"1", "true", "yes"}
SEMANTIC_CHUNK_MIN_SECTION_TOKENS = _env_int("HF_CDSS_SEMANTIC_CHUNK_MIN_SECTION_TOKENS", 600)

SECTION_SIMILARITY_THRESHOLD = _env_float("HF_CDSS_SECTION_SIMILARITY_THRESHOLD", 0.52)
SEMANTIC_CHUNK_BREAKPOINT_THRESHOLD = _env_float("HF_CDSS_SEMANTIC_CHUNK_BREAKPOINT", 0.42)
SEMANTIC_CHUNK_MIN_BLOCKS = _env_int("HF_CDSS_SEMANTIC_CHUNK_MIN_BLOCKS", 3)
SEMANTIC_CHUNK_MIN_TOKENS = _env_int("HF_CDSS_SEMANTIC_CHUNK_MIN_TOKENS", 120)
# Skip semantic breakpoints when a section explodes into too many sentence blocks
# (protects Ollama from huge /api/embed batches during chunking).
SEMANTIC_CHUNK_MAX_BLOCKS = _env_int("HF_CDSS_SEMANTIC_CHUNK_MAX_BLOCKS", 80)
# Truncate each embed input toward BGE-M3 context (~8192 tokens ≈ long chars).
EMBEDDING_MAX_INPUT_CHARS = _env_int("HF_CDSS_EMBEDDING_MAX_INPUT_CHARS", 12_000)
CLAIM_DEDUP_THRESHOLD = _env_float("HF_CDSS_CLAIM_DEDUP_THRESHOLD", 0.92)
CHUNK_DEDUP_THRESHOLD = _env_float("HF_CDSS_CHUNK_DEDUP_THRESHOLD", 0.95)
MINHASH_DEDUP_ENABLED = os.environ.get("HF_CDSS_MINHASH_DEDUP_ENABLED", "true").lower() in {"1", "true", "yes"}
MINHASH_NUM_PERM = _env_int("HF_CDSS_MINHASH_NUM_PERM", 64)
MINHASH_NUM_BANDS = _env_int("HF_CDSS_MINHASH_NUM_BANDS", 8)

DEFAULT_CHUNK_SIZE = _env_int("HF_CDSS_CHUNK_SIZE", 500)
DEFAULT_CHUNK_OVERLAP = _env_int("HF_CDSS_CHUNK_OVERLAP", 75)
# Shorter sections finish faster on qwen2.5:1.5b and reduce timeouts.
MAX_LLM_SECTION_CHARS = _env_int("HF_CDSS_MAX_LLM_SECTION_CHARS", 2500)
MAX_LLM_CLAIMS_PER_SECTION = _env_int("HF_CDSS_MAX_LLM_CLAIMS_PER_SECTION", 12)
