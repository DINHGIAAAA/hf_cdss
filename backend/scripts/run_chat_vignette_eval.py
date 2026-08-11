#!/usr/bin/env python3
"""Run chat vignette evaluation and save structured results.

Usage (from repo root):
  cd backend
  python scripts/run_chat_vignette_eval.py
  python scripts/run_chat_vignette_eval.py --limit 5 --case-id sq-vi-01
  python scripts/run_chat_vignette_eval.py --api-url http://127.0.0.1:8000/api/v1

Output: evaluation/reports/chat_vignette_results_<timestamp>.json
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# Resolve repo paths
SCRIPT_DIR = Path(__file__).resolve().parent
BACKEND_DIR = SCRIPT_DIR.parent
REPO_ROOT = BACKEND_DIR.parent
VIGNETTES_PATH = REPO_ROOT / "evaluation" / "chat" / "vignettes.json"
REPORTS_DIR = REPO_ROOT / "evaluation" / "reports"

if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_vignettes(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def _normalize_patient(patient: dict[str, Any] | None, *, case_id: str = "EVAL") -> dict[str, Any] | None:
    if not patient:
        return None
    return {**patient, "case_id": patient.get("case_id") or case_id}


def _serialize_patient(patient: dict[str, Any] | None) -> dict[str, Any] | None:
    if not patient:
        return None
    from app.schemas.patient import PatientProfile

    profile = PatientProfile.model_validate(_normalize_patient(patient))
    return profile.model_dump(mode="json")


def _extract_evidence(response: dict[str, Any]) -> list[dict[str, Any]]:
    evidence: list[dict[str, Any]] = []
    recommendation = response.get("recommendation") or {}
    for item in recommendation.get("recommendations") or []:
        for ref in item.get("evidence") or []:
            if isinstance(ref, str) and ref.strip():
                evidence.append({"source": "recommendation", "ref": ref, "drug_class": item.get("drug_class")})
    verification = response.get("verification") or {}
    citation = verification.get("citation_validation") or {}
    for support in citation.get("supports") or []:
        if isinstance(support, dict):
            evidence.append(
                {
                    "source": "citation_validation",
                    "target_id": support.get("target_id"),
                    "evidence_status": support.get("evidence_status"),
                    "message": support.get("message"),
                    "evidence_refs": support.get("evidence_refs") or [],
                }
            )
    graphrag = verification.get("graphrag_context") or {}
    for chunk in graphrag.get("evidence_chunks") or []:
        if isinstance(chunk, dict):
            evidence.append(
                {
                    "source": "graphrag",
                    "chunk_id": chunk.get("chunk_id"),
                    "document_id": chunk.get("document_id"),
                    "section": chunk.get("section"),
                    "text_preview": (chunk.get("text") or "")[:240],
                }
            )
    return evidence


def _recommendation_summary(response: dict[str, Any]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    recommendation = response.get("recommendation") or {}
    for item in recommendation.get("recommendations") or []:
        rows.append(
            {
                "class_id": str(item.get("class_id") or ""),
                "drug_class": str(item.get("drug_class") or ""),
                "status": str(item.get("status") or ""),
                "summary": str(item.get("plain_language_summary") or item.get("rationale") or "")[:400],
            }
        )
    return rows


async def _run_detection(message: str, patient: dict[str, Any] | None, language: str) -> dict[str, Any]:
    from app.modules.chat.language import detect_message_language, resolve_chat_language
    from app.modules.clinical_intake_extraction.semantic import detect_multi_question
    from app.modules.question_planner.service import plan_clinical_questions
    from app.schemas.patient import PatientProfile

    profile = PatientProfile.model_validate(_normalize_patient(patient)) if patient else None
    detected = detect_message_language(message, fallback=language)
    resolved = resolve_chat_language(message, language)
    rule_split = detect_multi_question(message)
    plan = await plan_clinical_questions(
        message,
        patient=profile,
        conversation_history=[],
        language=resolved,
    )
    return {
        "requested_language": language,
        "detected_language": detected,
        "resolved_language": resolved,
        "rule_multi_question_split": rule_split,
        "question_plan": plan.model_dump(mode="json"),
        "planned_question_count": len(plan.questions),
        "is_multi_question": plan.is_multi_question,
    }


async def _run_chat_inprocess(
    *,
    message: str,
    patient: dict[str, Any] | None,
    language: str,
    conversation_id: str | None,
    multi_question_action: str | None = None,
    pending_multi_question: dict[str, Any] | None = None,
) -> dict[str, Any]:
    from app.modules.chat.service import process_chat
    from app.schemas.chat import ChatRequest, PendingMultiQuestion
    from app.schemas.patient import PatientProfile

    profile = PatientProfile.model_validate(_normalize_patient(patient)) if patient else None
    pending = PendingMultiQuestion.model_validate(pending_multi_question) if pending_multi_question else None
    request = ChatRequest(
        message=message,
        conversation_id=conversation_id,
        patient=profile,
        language=language,
        multi_question_action=multi_question_action,
        pending_multi_question=pending,
    )
    response = await process_chat(request)
    return response.model_dump(mode="json")


async def _run_chat_api(
    *,
    api_url: str,
    api_key: str,
    message: str,
    patient: dict[str, Any] | None,
    language: str,
    conversation_id: str | None,
    multi_question_action: str | None = None,
    pending_multi_question: dict[str, Any] | None = None,
) -> dict[str, Any]:
    import httpx

    payload: dict[str, Any] = {
        "message": message,
        "language": language,
    }
    if conversation_id:
        payload["conversation_id"] = conversation_id
    if patient:
        payload["patient"] = _serialize_patient(patient)
    if multi_question_action:
        payload["multi_question_action"] = multi_question_action
    if pending_multi_question:
        payload["pending_multi_question"] = pending_multi_question

    headers = {"x-api-key": api_key} if api_key else {}
    async with httpx.AsyncClient(timeout=300.0) as client:
        response = await client.post(f"{api_url.rstrip('/')}/chat", json=payload, headers=headers)
        response.raise_for_status()
        return response.json()


async def _run_single_turn(
    *,
    case_id: str,
    turn_index: int,
    message: str,
    patient: dict[str, Any] | None,
    language: str,
    conversation_id: str | None,
    api_url: str | None,
    api_key: str,
    multi_question_action: str | None = None,
    pending_multi_question: dict[str, Any] | None = None,
) -> dict[str, Any]:
    started = time.perf_counter()
    timestamp = _utc_now()
    result: dict[str, Any] = {
        "case_id": case_id,
        "turn_index": turn_index,
        "timestamp": timestamp,
        "input": {
            "message": message,
            "language": language,
            "patient": patient,
            "conversation_id": conversation_id,
            "multi_question_action": multi_question_action,
        },
        "detection": None,
        "output": None,
        "error": None,
        "duration_ms": None,
    }
    try:
        result["detection"] = await _run_detection(message, patient, language)
        if api_url:
            chat_response = await _run_chat_api(
                api_url=api_url,
                api_key=api_key,
                message=message,
                patient=patient,
                language=language,
                conversation_id=conversation_id,
                multi_question_action=multi_question_action,
                pending_multi_question=pending_multi_question,
            )
        else:
            chat_response = await _run_chat_inprocess(
                message=message,
                patient=patient,
                language=language,
                conversation_id=conversation_id,
                multi_question_action=multi_question_action,
                pending_multi_question=pending_multi_question,
            )

        assistant = (chat_response.get("assistant_message") or {}).get("content") or ""
        result["output"] = {
            "status": chat_response.get("status"),
            "conversation_id": chat_response.get("conversation_id"),
            "answer": assistant,
            "missing_check": chat_response.get("missing_check"),
            "clinical_state": (chat_response.get("patient_draft") or {}).get("clinical_state"),
            "recommendation_summary": _recommendation_summary(chat_response),
            "evidence": _extract_evidence(chat_response),
            "verification_status": (chat_response.get("verification") or {}).get("status"),
            "llm_answer": chat_response.get("llm_answer"),
            "pending_multi_question": chat_response.get("pending_multi_question"),
            "needs_confirmation": chat_response.get("needs_confirmation"),
            "conflicts": chat_response.get("conflicts"),
            "question_plan": chat_response.get("question_plan"),
        }
        result["conversation_id"] = chat_response.get("conversation_id")
        result["pending_multi_question"] = chat_response.get("pending_multi_question")
    except Exception as exc:
        result["error"] = f"{type(exc).__name__}: {exc}"
    result["duration_ms"] = int((time.perf_counter() - started) * 1000)
    return result


async def _run_case(case: dict[str, Any], api_url: str | None, api_key: str) -> list[dict[str, Any]]:
    case_id = case["id"]
    category = case.get("category", "unknown")
    language = case.get("language", "vi")
    turns = case.get("turns")
    if not turns:
        turns = [{"message": case["message"], "patient": case.get("patient")}]

    conversation_id: str | None = None
    pending_multi: dict[str, Any] | None = None
    results: list[dict[str, Any]] = []

    for index, turn in enumerate(turns):
        turn_result = await _run_single_turn(
            case_id=case_id,
            turn_index=index,
            message=turn["message"],
            patient=turn.get("patient"),
            language=language,
            conversation_id=conversation_id,
            api_url=api_url,
            api_key=api_key,
            pending_multi_question=pending_multi,
        )
        turn_result["category"] = category
        results.append(turn_result)

        conversation_id = turn_result.get("conversation_id") or conversation_id
        pending_multi = turn_result.get("pending_multi_question")

        # Auto-continue multi-question threads when next turn not explicitly provided
        output = turn_result.get("output") or {}
        if (
            index == 0
            and len(turns) == 1
            and output.get("status") == "multi_question_confirm"
            and pending_multi
            and (pending_multi.get("remaining_qs") or [])
        ):
            continue_result = await _run_single_turn(
                case_id=case_id,
                turn_index=1,
                message="continue",
                patient=turn.get("patient"),
                language=language,
                conversation_id=conversation_id,
                api_url=api_url,
                api_key=api_key,
                multi_question_action="continue",
                pending_multi_question=pending_multi,
            )
            continue_result["category"] = category
            continue_result["auto_continue"] = True
            results.append(continue_result)

    return results


async def run_evaluation(args: argparse.Namespace) -> Path:
    from app.core.config import settings

    vignettes = _load_vignettes(Path(args.vignettes))
    cases = vignettes.get("cases") or []

    if args.case_id:
        cases = [case for case in cases if case.get("id") == args.case_id]
    if args.category:
        cases = [case for case in cases if case.get("category") == args.category]
    if args.limit:
        cases = cases[: args.limit]

    run_id = str(uuid.uuid4())
    started_at = _utc_now()
    all_results: list[dict[str, Any]] = []

    for case in cases:
        case_results = await _run_case(case, api_url=args.api_url, api_key=args.api_key or settings.api_keys.split(",")[0].strip())
        all_results.extend(case_results)
        print(f"  [{case['id']}] {len(case_results)} turn(s) — last status: {(case_results[-1].get('output') or {}).get('status', 'error')}")

    report = {
        "run_id": run_id,
        "started_at": started_at,
        "completed_at": _utc_now(),
        "vignettes_file": str(Path(args.vignettes).resolve()),
        "vignettes_version": vignettes.get("version"),
        "environment": settings.environment,
        "llm_model": settings.llm_model,
        "question_planner_model": settings.question_planner_model,
        "mode": "api" if args.api_url else "inprocess",
        "api_url": args.api_url,
        "case_count": len(cases),
        "result_count": len(all_results),
        "results": all_results,
    }

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    timestamp_slug = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    output_path = Path(args.output) if args.output else REPORTS_DIR / f"chat_vignette_results_{timestamp_slug}.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as handle:
        json.dump(report, handle, ensure_ascii=False, indent=2, default=str)

    latest_path = REPORTS_DIR / "chat_vignette_results_latest.json"
    with latest_path.open("w", encoding="utf-8") as handle:
        json.dump(report, handle, ensure_ascii=False, indent=2, default=str)

    return output_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Run HF CDSS chat vignette evaluation")
    parser.add_argument("--vignettes", default=str(VIGNETTES_PATH), help="Path to vignettes JSON")
    parser.add_argument("--output", default=None, help="Output JSON path (default: evaluation/reports/...)")
    parser.add_argument("--limit", type=int, default=None, help="Max number of cases to run")
    parser.add_argument("--case-id", default=None, help="Run a single case by id")
    parser.add_argument("--category", default=None, help="Filter by category")
    parser.add_argument("--api-url", default=None, help="Use live API instead of in-process (e.g. http://127.0.0.1:8000/api/v1)")
    parser.add_argument("--api-key", default=None, help="API key for live API mode")
    args = parser.parse_args()

    print(f"Running {args.case_id or args.category or 'all'} vignettes...")
    output = asyncio.run(run_evaluation(args))
    print(f"Saved: {output}")
    print(f"Latest: {REPORTS_DIR / 'chat_vignette_results_latest.json'}")


if __name__ == "__main__":
    main()
