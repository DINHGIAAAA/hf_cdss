"""HyDE retrieval query expansion for GraphRAG semantic search."""

from __future__ import annotations

import hashlib
import json
import logging
import re
import threading
import time
from datetime import datetime, timedelta
from typing import Any

from app.core.config import settings
from app.core.http_client import get_async_client
from app.core.llm_runtime import chat_completions_url, llm_auth_headers, llm_chat_completions_enabled
from app.core.metrics import increment, observe
from app.modules.chat.clinical_state import state_query_text
from app.prompts.hyde_retrieval import HYDE_RETRIEVAL_SYSTEM_PROMPT
from app.schemas.patient import PatientProfile


logger = logging.getLogger(__name__)

_CACHE_LOCK = threading.Lock()
_HYDE_CACHE: dict[str, tuple[datetime, str]] = {}


def hyde_retrieval_enabled() -> bool:
    return bool(getattr(settings, "hyde_retrieval_enabled", False))


def _hyde_model() -> str:
    configured = str(getattr(settings, "hyde_retrieval_model", "") or "").strip()
    return configured or settings.llm_model


def _cache_ttl_seconds() -> int:
    return int(getattr(settings, "hyde_retrieval_cache_ttl_seconds", 600))


def _cache_max_entries() -> int:
    return int(getattr(settings, "hyde_retrieval_cache_max_entries", 256))


def _min_query_chars() -> int:
    return int(getattr(settings, "hyde_retrieval_min_query_chars", 8))


def _sanitize_hyde_document(text: str) -> str | None:
    cleaned = re.sub(r"\s+", " ", (text or "").strip())
    cleaned = cleaned.strip("\"'`")
    if len(cleaned) < 40:
        return None
    if cleaned.startswith("{") or cleaned.startswith("["):
        return None
    return cleaned[:900]


def _patient_context_lines(
    patient: PatientProfile,
    *,
    clinical_state: dict[str, Any] | None,
    conversation_history: list[str] | None,
) -> list[str]:
    lines: list[str] = []
    if clinical_state:
        if intent := clinical_state.get("intent"):
            lines.append(f"Clinical intent: {intent}")
        if hf_type := clinical_state.get("hf_type"):
            lines.append(f"HF phenotype: {hf_type}")
        key_values = clinical_state.get("key_values") or {}
        labs = []
        for key in ("lvef", "egfr", "potassium", "systolic_bp", "heart_rate", "creatinine", "inr"):
            value = key_values.get(key)
            if value is not None:
                labs.append(f"{key}={value}")
        if labs:
            lines.append("Key values: " + ", ".join(labs))
        focus = clinical_state.get("focus_medication_classes") or []
        if focus:
            lines.append("Focus drug classes: " + ", ".join(str(item) for item in focus))
        mentioned = clinical_state.get("mentioned_medications") or []
        if mentioned:
            names = [
                str(item.get("name") or item)
                if isinstance(item, dict)
                else str(item)
                for item in mentioned
            ]
            lines.append("Mentioned medications: " + ", ".join(names))
        safety = clinical_state.get("safety_state") or {}
        active_flags = [key for key, active in safety.items() if active is True]
        if active_flags:
            lines.append("Safety flags: " + ", ".join(active_flags))
    else:
        summary_bits = []
        if patient.lvef is not None:
            summary_bits.append(f"LVEF {patient.lvef}%")
        if patient.egfr is not None:
            summary_bits.append(f"eGFR {patient.egfr}")
        if patient.potassium is not None:
            summary_bits.append(f"potassium {patient.potassium}")
        if patient.systolic_bp is not None:
            summary_bits.append(f"SBP {patient.systolic_bp}")
        if patient.heart_rate is not None:
            summary_bits.append(f"HR {patient.heart_rate}")
        if summary_bits:
            lines.append("Patient summary: " + "; ".join(summary_bits))

    if patient.current_medications:
        lines.append("Current medications: " + ", ".join(patient.current_medications))
    if patient.comorbidities:
        lines.append("Comorbidities: " + ", ".join(patient.comorbidities))

    if conversation_history:
        recent = [turn.strip() for turn in conversation_history if turn and turn.strip()][-3:]
        if recent:
            lines.append("Recent clinician messages: " + " | ".join(recent))

    if clinical_state:
        state_text = state_query_text(clinical_state)
        if state_text:
            lines.append(f"Structured state: {state_text}")

    return lines


def _build_hyde_user_prompt(
    query: str,
    patient: PatientProfile,
    *,
    clinical_state: dict[str, Any] | None,
    conversation_history: list[str] | None,
) -> str:
    context_lines = _patient_context_lines(
        patient,
        clinical_state=clinical_state,
        conversation_history=conversation_history,
    )
    context_block = "\n".join(f"- {line}" for line in context_lines) if context_lines else "- No structured context supplied."
    return (
        f"Clinician question:\n{query.strip()}\n\n"
        f"Patient and conversation context:\n{context_block}\n\n"
        "Write the hypothetical guideline excerpt now."
    )


def _cache_key(
    query: str,
    patient: PatientProfile,
    *,
    clinical_state: dict[str, Any] | None,
    conversation_history: list[str] | None,
) -> str:
    payload = {
        "query": query.strip().lower(),
        "case_id": patient.case_id,
        "clinical_state": clinical_state or {},
        "conversation_history": conversation_history or [],
        "model": _hyde_model(),
    }
    digest = hashlib.sha256(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()
    return f"hyde:{digest}"


def _read_cache(key: str) -> str | None:
    with _CACHE_LOCK:
        entry = _HYDE_CACHE.get(key)
        if not entry:
            return None
        timestamp, document = entry
        if datetime.now() - timestamp > timedelta(seconds=_cache_ttl_seconds()):
            _HYDE_CACHE.pop(key, None)
            return None
        return document


def _write_cache(key: str, document: str) -> None:
    with _CACHE_LOCK:
        if len(_HYDE_CACHE) >= _cache_max_entries():
            oldest_key = min(_HYDE_CACHE.items(), key=lambda item: item[1][0])[0]
            _HYDE_CACHE.pop(oldest_key, None)
        _HYDE_CACHE[key] = (datetime.now(), document)


def invalidate_hyde_cache() -> None:
    with _CACHE_LOCK:
        _HYDE_CACHE.clear()


def should_expand_with_hyde(query: str | None) -> bool:
    if not hyde_retrieval_enabled():
        return False
    if not llm_chat_completions_enabled():
        return False
    if not query or len(query.strip()) < _min_query_chars():
        return False
    return True


async def generate_hyde_document(
    query: str,
    patient: PatientProfile,
    *,
    clinical_state: dict[str, Any] | None = None,
    conversation_history: list[str] | None = None,
) -> str | None:
    if not should_expand_with_hyde(query):
        return None

    cache_key = _cache_key(query, patient, clinical_state=clinical_state, conversation_history=conversation_history)
    cached = _read_cache(cache_key)
    if cached:
        increment("hf_cdss_hyde_requests_total", {"result": "cache_hit"})
        return cached

    started = time.perf_counter()
    try:
        client = get_async_client(
            "hyde_retrieval",
            float(getattr(settings, "hyde_retrieval_timeout_seconds", 20.0)),
            max_connections=4,
        )
        response = await client.post(
            chat_completions_url(),
            headers=llm_auth_headers(),
            json={
                "model": _hyde_model(),
                "messages": [
                    {"role": "system", "content": HYDE_RETRIEVAL_SYSTEM_PROMPT},
                    {
                        "role": "user",
                        "content": _build_hyde_user_prompt(
                            query,
                            patient,
                            clinical_state=clinical_state,
                            conversation_history=conversation_history,
                        )[:6000],
                    },
                ],
                "temperature": 0,
                "max_tokens": int(getattr(settings, "hyde_retrieval_max_tokens", 220)),
            },
        )
        response.raise_for_status()
        choices = response.json().get("choices", [])
        content = choices[0].get("message", {}).get("content", "") if choices else ""
        document = _sanitize_hyde_document(content)
        if not document:
            increment("hf_cdss_hyde_requests_total", {"result": "invalid_output"})
            return None
        _write_cache(cache_key, document)
        increment("hf_cdss_hyde_requests_total", {"result": "success"})
        return document
    except Exception as exc:
        logger.warning("HyDE retrieval expansion failed: %s", exc)
        increment("hf_cdss_hyde_requests_total", {"result": "error"})
        return None
    finally:
        observe("hf_cdss_hyde_latency_seconds", time.perf_counter() - started)


def build_semantic_retrieval_query(
    *,
    baseline_query: str,
    hyde_document: str | None,
) -> str:
    baseline = baseline_query.strip()
    if not hyde_document:
        return baseline
    if getattr(settings, "hyde_retrieval_combine_baseline", True):
        return f"{hyde_document}\n\n{baseline}"[:4000]
    return hyde_document
