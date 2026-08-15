"""Sync Ollama chat-completions client for structured ingestion extraction."""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import threading
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Callable, Iterator

import httpx

from scraper.semantic import config

logger = logging.getLogger(__name__)

try:
    import fcntl
except ImportError:  # Windows native runs
    fcntl = None  # type: ignore[assignment]

_thread_slots: dict[str, threading.Semaphore] = {}
_thread_slots_lock = threading.Lock()

# Clinical priority patterns for context optimization
LLM_PRIORITY_PATTERNS = [
    r"contraindicat",
    r"dos(e|ing|age)",
    r"warning",
    r"precaution",
    r"interact",
    r"contraindicated",
    r"adverse",
    r"renal",
    r"hepatic",
    r"pregnan",
    r"pediatr",
    r"geriatr",
    r"monitor",
    r"hyperkalem",
    r"hypotens",
]


def _estimate_tokens(text: str) -> int:
    """Rough token estimation (avg 4 chars per token)."""
    return len(text) // 4


def _split_into_sentences(text: str) -> list[str]:
    """Split text into sentences."""
    # Simple sentence splitting
    sentence_pattern = re.compile(r'(?<=[.!?])\s+')
    return sentence_pattern.split(text)


def prepare_section_context(
    text: str,
    max_tokens: int = 2000,
) -> str:
    """Extract most relevant portion of long sections using semantic priority.

    For long sections, prioritize content containing clinical importance markers
    (contraindications, dosing, warnings, interactions) over less critical content.
    """
    chunk_size = _estimate_tokens(text)

    if chunk_size <= max_tokens:
        return text

    # Extract sentences with priority patterns
    sentences = _split_into_sentences(text)
    priority_sentences = []
    regular_sentences = []

    for sentence in sentences:
        sentence = sentence.strip()
        if not sentence:
            continue
        # Check if sentence matches priority patterns
        is_priority = any(
            re.search(pattern, sentence, re.IGNORECASE)
            for pattern in LLM_PRIORITY_PATTERNS
        )
        if is_priority:
            priority_sentences.append(sentence)
        else:
            regular_sentences.append(sentence)

    # If enough priority content, use it first
    priority_tokens = _estimate_tokens(" ".join(priority_sentences))
    if priority_tokens > max_tokens * 0.6:
        # Greedily select priority sentences up to limit
        selected = []
        for s in priority_sentences:
            if _estimate_tokens(" ".join(selected + [s])) <= max_tokens:
                selected.append(s)
            else:
                break
        return " ".join(selected)

    # Otherwise, combine priority + regular up to limit
    selected = priority_sentences.copy()
    for s in regular_sentences:
        if _estimate_tokens(" ".join(selected + [s])) <= max_tokens:
            selected.append(s)
        else:
            break

    if not selected:
        # Fallback: head + tail
        half = max_tokens // 2
        return text[:half * 4] + "\n\n... [truncated] ...\n\n" + text[-half * 4:]

    return " ".join(selected)


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
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code == 401 or exc.response.status_code == 403:
            logger.error("LLM auth failed (%d) — check LLM_API_KEY. Pipeline will run in regex-only mode.", exc.response.status_code)
        else:
            logger.warning("LLM health check failed (%d): %s", exc.response.status_code, exc)
        return False
    except OSError as exc:
        logger.warning("LLM unreachable (network error): %s", exc)
        return False
    except Exception as exc:
        logger.warning("LLM availability check failed: %s", exc)
        return False


def _cache_dir() -> Path | None:
    if not config.INGESTION_LLM_CACHE_ENABLED:
        return None
    from scraper.paths import data_root

    raw = (config.INGESTION_LLM_CACHE_DIR or "").strip()
    path = Path(raw) if raw else data_root() / ".cache" / "llm_claims"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _enforce_cache_size_limit(cache_root: Path, max_entries: int = 5000) -> None:
    """Evict oldest cache entries if cache exceeds max_entries."""
    try:
        cache_files = sorted(
            cache_root.glob("*.json"),
            key=lambda f: f.stat().st_mtime,
        )
        if len(cache_files) > max_entries:
            # Remove oldest 20% of entries
            evict_count = max(100, len(cache_files) - int(max_entries * 0.8))
            for cache_file in cache_files[:evict_count]:
                cache_file.unlink(missing_ok=True)
    except OSError:
        pass  # Ignore errors during cleanup


def _cache_key(system_prompt: str, user_prompt: str, *, max_tokens: int, model: str) -> str:
    raw = f"{model}|{max_tokens}|{system_prompt}|||{user_prompt}"
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()


def _read_cache(key: str) -> dict[str, Any] | None:
    cache_root = _cache_dir()
    if cache_root is None or not config.INGESTION_LLM_CACHE_ENABLED:
        return None
    cache_file = cache_root / f"{key}.json"
    if not cache_file.exists():
        return None
    try:
        payload = json.loads(cache_file.read_text(encoding="utf-8"))
        return payload if isinstance(payload, dict) else None
    except (OSError, json.JSONDecodeError):
        return None


def _write_cache(key: str, payload: dict[str, Any]) -> None:
    cache_root = _cache_dir()
    if cache_root is None or not config.INGESTION_LLM_CACHE_ENABLED:
        return
    # Enforce size limit before writing
    _enforce_cache_size_limit(cache_root, config.LLM_CACHE_MAX_ENTRIES)
    cache_file = cache_root / f"{key}.json"
    cache_file.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def _shrink_user_prompt(user_prompt: str) -> str:
    """Halve text/evidence on timeout retry so small models can finish."""
    try:
        data = json.loads(user_prompt)
    except json.JSONDecodeError:
        return user_prompt[: max(800, len(user_prompt) // 2)]
    if not isinstance(data, dict):
        return user_prompt[: max(800, len(user_prompt) // 2)]
    # Shrink text field (used by ingestion/claim extraction).
    text = data.get("text")
    if isinstance(text, str) and text:
        data["text"] = text[: max(800, len(text) // 2)]
    # Shrink evidence field (used by condition refinement).
    evidence = data.get("evidence")
    if isinstance(evidence, str) and evidence:
        data["evidence"] = evidence[: max(600, len(evidence) // 2)]
    return json.dumps(data, ensure_ascii=False)


def _http_timeout(seconds: float) -> httpx.Timeout:
    read = max(30.0, seconds)
    return httpx.Timeout(connect=10.0, read=read, write=30.0, pool=30.0)


def _slot_count() -> int:
    return max(1, int(config.LLM_CONCURRENCY))


def _slot_key(model: str | None) -> str:
    raw = (model or config.INGESTION_LLM_MODEL or "default").strip() or "default"
    if not getattr(config, "LLM_SLOTS_PER_MODEL", True):
        return "shared"
    # Filesystem-safe model id (qwen2.5:1.5b → qwen2.5_1.5b)
    safe = re.sub(r"[^A-Za-z0-9._-]+", "_", raw)
    return safe[:80] or "default"


def _slot_dir() -> Path:
    raw = (os.environ.get("HF_CDSS_LLM_SLOT_DIR") or "").strip()
    if raw:
        path = Path(raw)
    else:
        try:
            from scraper.paths import data_root

            path = data_root() / ".cache" / "llm_inflight_slots"
        except Exception:  # noqa: BLE001
            path = Path(os.environ.get("TMPDIR") or os.environ.get("TEMP") or "/tmp") / "hf_cdss_llm_slots"
    path.mkdir(parents=True, exist_ok=True)
    return path


@contextmanager
def _llm_inflight_slot(model: str | None = None) -> Iterator[None]:
    """Occupy an LLM slot only while an HTTP generation request is in flight.

    Slots are keyed by model (default) so different models do not share one pool.
    Cross-process (Linux/Airflow): flock on N slot files per model.
    Fallback (Windows/tests): threading.Semaphore — process-local only.
    Cache hits and non-LLM work never enter this context.
    """
    slots = _slot_count()
    key = _slot_key(model)

    if fcntl is None:
        with _thread_slots_lock:
            sem = _thread_slots.get(key)
            if sem is None or getattr(sem, "_hf_slots", None) != slots:
                sem = threading.Semaphore(slots)
                setattr(sem, "_hf_slots", slots)
                _thread_slots[key] = sem
        sem.acquire()
        try:
            yield
        finally:
            sem.release()
        return

    lock_dir = _slot_dir() / key
    lock_dir.mkdir(parents=True, exist_ok=True)
    handles: list[Any] = []
    acquired = None
    try:
        while acquired is None:
            for index in range(slots):
                path = lock_dir / f"slot_{index}.lock"
                handle = path.open("a+", encoding="utf-8")
                try:
                    fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                except BlockingIOError:
                    handle.close()
                    continue
                handles.append(handle)
                acquired = handle
                break
            if acquired is None:
                time.sleep(0.05)
        yield
    finally:
        if acquired is not None:
            try:
                fcntl.flock(acquired.fileno(), fcntl.LOCK_UN)
            except Exception:  # noqa: BLE001
                pass
        for handle in handles:
            try:
                handle.close()
            except Exception:  # noqa: BLE001
                pass


def _call_llm_json_raw(
    system_prompt: str,
    user_prompt: str,
    *,
    max_tokens: int,
    model: str | None = None,
    timeout_seconds: float | None = None,
    num_ctx: int | None = None,
) -> dict[str, Any] | None:
    url = f"{config.LLM_BASE_URL.rstrip('/')}/chat/completions"
    max_attempts = max(1, config.LLM_MAX_RETRIES + 1)
    current_prompt = user_prompt
    current_max_tokens = max(64, max_tokens)
    resolved_model = model or config.INGESTION_LLM_MODEL
    resolved_timeout = (
        float(timeout_seconds)
        if timeout_seconds is not None
        else float(config.INGESTION_LLM_TIMEOUT_SECONDS)
    )
    # qwen2.5:7b native context is 32k; 32b variants reach 128k.
    # Only override if caller explicitly requests a smaller context window.
    resolved_ctx = int(num_ctx) if num_ctx is not None else 32768

    for attempt in range(1, max_attempts + 1):
        payload = {
            "model": resolved_model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": current_prompt},
            ],
            "temperature": 0,
            "max_tokens": current_max_tokens,
            # Keep Ollama generation bounded so CPU runs finish before client timeout.
            "options": {
                "num_predict": current_max_tokens,
                "num_ctx": resolved_ctx,
            },
        }
        try:
            # Hold a per-model shared slot only for the HTTP round-trip.
            with _llm_inflight_slot(resolved_model):
                with httpx.Client(timeout=_http_timeout(resolved_timeout)) as client:
                    response = client.post(
                        url,
                        headers={"Content-Type": "application/json"},
                        json=payload,
                    )
                    response.raise_for_status()
                    choices = response.json().get("choices", [])
                    content = choices[0].get("message", {}).get("content", "") if choices else ""
            return extract_json_object(content)
        except Exception as exc:
            retryable = isinstance(exc, httpx.TimeoutException) or "timed out" in str(exc).lower()
            if retryable and attempt < max_attempts:
                current_prompt = _shrink_user_prompt(current_prompt)
                current_max_tokens = max(64, current_max_tokens // 2)
                logger.warning(
                    "LLM request timed out (attempt %s/%s, model=%s, timeout=%.0fs); "
                    "retrying with shorter prompt (max_tokens=%s)",
                    attempt,
                    max_attempts,
                    resolved_model,
                    resolved_timeout,
                    current_max_tokens,
                )
                continue
            logger.warning("LLM request failed: %s", exc)
            return None

    return None


def call_llm_json(
    system_prompt: str,
    user_prompt: str,
    *,
    max_tokens: int | None = None,
    model: str | None = None,
    timeout_seconds: float | None = None,
    num_ctx: int | None = None,
    cache_predicate: Callable[[dict[str, Any]], bool] | None = None,
) -> dict[str, Any] | None:
    max_tokens = max_tokens or config.LLM_MAX_TOKENS
    resolved_model = model or config.INGESTION_LLM_MODEL
    # If explicit timeout_seconds passed, use it directly
    if timeout_seconds is not None:
        resolved_timeout = float(timeout_seconds)
    elif model == config.CONDITION_REFINE_LLM_MODEL:
        resolved_timeout = float(config.CONDITION_REFINE_LLM_TIMEOUT_SECONDS)
    else:
        resolved_timeout = float(config.INGESTION_LLM_TIMEOUT_SECONDS)
    cache_key = _cache_key(system_prompt, user_prompt, max_tokens=max_tokens, model=resolved_model)
    cached = _read_cache(cache_key)
    if cached is not None:
        if cache_predicate is None or cache_predicate(cached):
            return cached
        # Ignore poisoned/useless cache entries (e.g. empty conditions with high conf).

    payload = _call_llm_json_raw(
        system_prompt,
        user_prompt,
        max_tokens=max_tokens,
        model=resolved_model,
        timeout_seconds=resolved_timeout,
        num_ctx=num_ctx,
    )
    if payload and (cache_predicate is None or cache_predicate(payload)):
        _write_cache(cache_key, payload)
    return payload
