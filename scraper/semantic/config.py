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
# Condition refine needs structured JSON; prefer larger model than ingestion extract.
CONDITION_REFINE_LLM_MODEL = os.environ.get("HF_CDSS_CONDITION_REFINE_LLM_MODEL", LLM_MODEL)
LLM_TIMEOUT_SECONDS = _env_float("HF_CDSS_LLM_TIMEOUT_SECONDS", 45.0)
CONDITION_REFINE_LLM_MAX_TOKENS = _env_int("HF_CDSS_CONDITION_REFINE_LLM_MAX_TOKENS", 250)
# Longer timeout for qwen2.5:7b on CPU (prompt processing + generation):
#   - qwen2.5:7b on CPU ~5-15 tokens/s generation
#   - ~200-token JSON response = 15-40s generation + 30-60s prompt = 60-100s typical
#   - 300s gives margin for spikes without indefinite hangs
CONDITION_REFINE_LLM_TIMEOUT_SECONDS = _env_float(
    "HF_CDSS_CONDITION_REFINE_LLM_TIMEOUT_SECONDS",
    max(LLM_TIMEOUT_SECONDS, 300.0),
)
# Claim extraction on CPU Ollama needs MUCH longer; set to 600s for reliability
INGESTION_LLM_TIMEOUT_SECONDS = _env_float(
    "HF_CDSS_INGESTION_LLM_TIMEOUT_SECONDS",
    max(LLM_TIMEOUT_SECONDS, 600.0),
)
LLM_MAX_RETRIES = _env_int("HF_CDSS_LLM_MAX_RETRIES", 2)
LLM_MAX_TOKENS = _env_int("HF_CDSS_INGESTION_LLM_MAX_TOKENS", 600)
LLM_CONCURRENCY = _env_int("HF_CDSS_LLM_CONCURRENCY", 4)
# When true (default), each model name has its own in-flight slot pool so
# e.g. qwen2.5:1.5b extract and qwen2.5:7b refine do not block each other client-side.
LLM_SLOTS_PER_MODEL = os.environ.get("HF_CDSS_LLM_SLOTS_PER_MODEL", "true").lower() in {
    "1",
    "true",
    "yes",
}
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
EMBEDDING_BATCH_SIZE = _env_int("HF_CDSS_EMBEDDING_BATCH_SIZE", 32)
EMBEDDING_PARALLEL_WORKERS = _env_int("HF_CDSS_EMBEDDING_PARALLEL_WORKERS", 4)
# bge-m3 on CPU often needs > LLM chat timeout; keep a dedicated budget.
EMBEDDING_TIMEOUT_MIN_SECONDS = 300.0
EMBEDDING_TIMEOUT_SECONDS = max(
    EMBEDDING_TIMEOUT_MIN_SECONDS,
    _env_float(
        "HF_CDSS_EMBEDDING_TIMEOUT_SECONDS",
        max(LLM_TIMEOUT_SECONDS, EMBEDDING_TIMEOUT_MIN_SECONDS),
    ),
)
EMBEDDING_BATCH_TIMEOUT_CAP_SECONDS = _env_float(
    "HF_CDSS_EMBEDDING_BATCH_TIMEOUT_CAP_SECONDS",
    900.0,
)
EMBEDDING_MAX_RETRIES = _env_int("HF_CDSS_EMBEDDING_MAX_RETRIES", 2)
# Ollama keep_alive for embed requests. "0" unloads after each call (slow on CPU ingestion).
# Use "5m" during batch ingest; set "0" on shared Ollama if chat models must not wait on bge-m3.
EMBEDDING_KEEP_ALIVE = os.environ.get("HF_CDSS_EMBEDDING_KEEP_ALIVE", "5m").strip() or "5m"
EMBEDDING_CACHE_ENABLED = os.environ.get("HF_CDSS_EMBEDDING_CACHE_ENABLED", "true").lower() in {"1", "true", "yes"}


def embedding_batch_timeout_seconds(batch_len: int, base_timeout: float | None = None) -> float:
    """Scale HTTP timeout for multi-text /api/embed batches on CPU Ollama."""
    base = base_timeout if base_timeout is not None else EMBEDDING_TIMEOUT_SECONDS
    if batch_len <= 1:
        return base
    scaled = base * max(1.0, batch_len / 4.0)
    return min(EMBEDDING_BATCH_TIMEOUT_CAP_SECONDS, scaled)


EMBEDDING_CACHE_DIR = _resolved_cache_dir("HF_CDSS_EMBEDDING_CACHE_DIR", "embeddings")
EMBEDDING_DEDUP_ENABLED = os.environ.get("HF_CDSS_EMBEDDING_DEDUP_ENABLED", "false").lower() in {"1", "true", "yes"}

SEMANTIC_CHUNK_ENABLED = os.environ.get("HF_CDSS_SEMANTIC_CHUNK_ENABLED", "true").lower() in {"1", "true", "yes"}
SEMANTIC_CHUNK_MIN_SECTION_TOKENS = _env_int("HF_CDSS_SEMANTIC_CHUNK_MIN_SECTION_TOKENS", 1000)

SECTION_SIMILARITY_THRESHOLD = _env_float("HF_CDSS_SECTION_SIMILARITY_THRESHOLD", 0.52)
# Embed scores in [borderline_low, keep_threshold) get a cheap LLM keep/drop check.
SECTION_BORDERLINE_LOW_THRESHOLD = _env_float("HF_CDSS_SECTION_BORDERLINE_LOW_THRESHOLD", 0.40)

# Adaptive threshold configuration - per-section type thresholds
SECTION_ADAPTIVE_THRESHOLD_ENABLED = os.environ.get(
    "HF_CDSS_SECTION_ADAPTIVE_THRESHOLD_ENABLED", "true"
).lower() in {"1", "true", "yes"}

# Per-section thresholds (higher priority = lower threshold = more permissive)
SECTION_TYPE_THRESHOLDS: dict[str, float] = {
    # High-priority: lower threshold (more permissive)
    "BOXED WARNING": 0.40,
    "BLACK BOX WARNING": 0.40,
    "CONTRAINDICATIONS": 0.42,
    "WARNINGS AND PRECAUTIONS": 0.45,
    "DRUG INTERACTIONS": 0.45,
    "DOSAGE AND ADMINISTRATION": 0.48,
    "RENAL IMPAIRMENT": 0.48,
    # Medium priority
    "INDICATIONS AND USAGE": 0.50,
    "ADVERSE REACTIONS": 0.50,
    "USE IN SPECIFIC POPULATIONS": 0.48,
    # Lower priority: higher threshold
    "CLINICAL PHARMACOLOGY": 0.55,
    "CLINICAL STUDIES": 0.55,
    "DESCRIPTION": 0.58,
    "HOW SUPPLIED": 0.60,
}

# Per-guideline-topic thresholds
GUIDELINE_TOPIC_THRESHOLDS: dict[str, float] = {
    # High clinical impact
    "contraindications": 0.42,
    "warnings": 0.44,
    "drug interactions": 0.44,
    "monitoring": 0.46,
    "dosing": 0.48,
    "renal dysfunction": 0.46,
    "hyperkalemia": 0.44,
    # Medium impact
    "recommendations": 0.50,
    "drug therapy": 0.50,
    "heart failure phenotypes": 0.50,
    "atrial fibrillation": 0.50,
    "hypertension": 0.52,
    "diabetes": 0.52,
    "comorbidities": 0.52,
    # Lower impact
    "biomarkers": 0.54,
    "liver function": 0.54,
    "mortality": 0.55,
    "hospitalization": 0.55,
}

# Threshold relaxation for longer content
MIN_TEXT_LENGTH_FOR_RELAXED_THRESHOLD = 200
THRESHOLD_RELAXATION_AMOUNT = 0.03
MAX_THRESHOLD_REDUCTION = 0.05


def get_adaptive_threshold(
    section: str,
    topic: str,
    text_length: int,
    source_type: str,
) -> float:
    """Calculate adaptive threshold based on section type and content."""
    if not SECTION_ADAPTIVE_THRESHOLD_ENABLED:
        return SECTION_SIMILARITY_THRESHOLD

    section_upper = section.upper() if section else ""

    if source_type == "drug_label":
        base_threshold = SECTION_TYPE_THRESHOLDS.get(
            section_upper,
            SECTION_SIMILARITY_THRESHOLD
        )
    else:
        base_threshold = GUIDELINE_TOPIC_THRESHOLDS.get(
            topic.lower(),
            SECTION_SIMILARITY_THRESHOLD
        )

    # Relax threshold for longer, substantive content
    reduction = 0.0
    if text_length >= MIN_TEXT_LENGTH_FOR_RELAXED_THRESHOLD:
        reduction = min(
            THRESHOLD_RELAXATION_AMOUNT,
            (text_length / 1000) * THRESHOLD_RELAXATION_AMOUNT
        )

    return max(
        base_threshold - reduction,
        base_threshold - MAX_THRESHOLD_REDUCTION
    )

SECTION_BORDERLINE_LLM_ENABLED = os.environ.get("HF_CDSS_SECTION_BORDERLINE_LLM_ENABLED", "true").lower() in {
    "1",
    "true",
    "yes",
}
SECTION_BORDERLINE_LLM_MAX = _env_int("HF_CDSS_SECTION_BORDERLINE_LLM_MAX", 800)
SECTION_BORDERLINE_LLM_MAX_TOKENS = _env_int("HF_CDSS_SECTION_BORDERLINE_LLM_MAX_TOKENS", 120)
# Rescue low-embed sections (< borderline_low) when body text has high-signal clinical cues.
SECTION_LOW_SCORE_TEXT_RESCUE_ENABLED = os.environ.get(
    "HF_CDSS_SECTION_LOW_SCORE_TEXT_RESCUE_ENABLED",
    "true",
).lower() in {"1", "true", "yes"}
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

# Strict mode for claim extraction - disabled by default for balanced filtering
STRICT_MODE_ENABLED = os.environ.get("HF_CDSS_STRICT_MODE_ENABLED", "false").lower() in {"1", "true", "yes"}
# Minimum confidence threshold for claims
CLAIM_MIN_CONFIDENCE = _env_float("HF_CDSS_CLAIM_MIN_CONFIDENCE", 0.7)

DEFAULT_CHUNK_SIZE = _env_int("HF_CDSS_CHUNK_SIZE", 500)
DEFAULT_CHUNK_OVERLAP = _env_int("HF_CDSS_CHUNK_OVERLAP", 75)
# Shorter sections finish faster on qwen2.5:1.5b and reduce timeouts.
MAX_LLM_SECTION_CHARS = _env_int("HF_CDSS_MAX_LLM_SECTION_CHARS", 2000)
MAX_LLM_CLAIMS_PER_SECTION = _env_int("HF_CDSS_MAX_LLM_CLAIMS_PER_SECTION", 6)
