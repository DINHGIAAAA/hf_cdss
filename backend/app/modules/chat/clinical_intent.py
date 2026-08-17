"""Clinical intent helpers for dose visibility and planner alignment."""

from __future__ import annotations

from typing import Any

DOSE_PLAN_INTENTS = frozenset({"dose_adjustment"})

# A standalone new clinical question about a named class/action shouldn't
# inherit focus from whatever an unrelated previous turn's answer happened to
# mention — that reads as still discussing the old topic. Shared between
# chat/clinical_state.py (persisting focus_medication_classes) and
# explanation/question_focus.py (re-deriving focus at answer time), which
# independently merge in prior-assistant-message keywords and must agree on
# when that's appropriate.
STANDALONE_QUESTION_INTENTS = frozenset(
    {"dose_adjustment", "start_medication", "stop_or_avoid", "safety_check", "choice_question"}
)

PLANNER_INTENT_MAP: dict[str, str] = {
    "general": "recommendation",
    "dose_adjustment": "dose_adjustment",
    "start_medication": "start_medication",
    "safety_check": "safety_check",
    "choice_question": "choice_question",
    "definition": "definition",
    "evidence_question": "evidence_question",
    "stop_or_avoid": "stop_or_avoid",
    "follow_up_detail": "follow_up_detail",
    "recommendation": "recommendation",
}


def map_planner_intent(planner_intent: str | None) -> str | None:
    raw = str(planner_intent or "").strip().lower()
    if not raw:
        return None
    return PLANNER_INTENT_MAP.get(raw, raw)


def should_compute_dose_plans(intent: str | None) -> bool:
    return (intent or "recommendation") in DOSE_PLAN_INTENTS


def should_include_dose_in_llm_payload(intent: str | None) -> bool:
    return should_compute_dose_plans(intent)


def merge_planned_question_intent(
    state: dict[str, Any],
    planned: Any | None,
) -> dict[str, Any]:
    """Apply per-question planner intent/focus onto turn clinical_state."""
    if planned is None:
        return state

    updated = dict(state)
    mapped = map_planner_intent(getattr(planned, "intent", None))
    if mapped:
        updated["intent"] = mapped

    focus_ids = getattr(planned, "focus_class_ids", None) or []
    focus_ids = sorted({str(value).strip().lower() for value in focus_ids if str(value).strip()})
    if focus_ids:
        updated["focus_class_ids"] = focus_ids
        updated["focus_medication_classes"] = focus_ids

    # Track current question being answered (for multi-Q flow)
    planned_text = getattr(planned, "text", None)
    if planned_text:
        updated["current_question"] = planned_text

    return updated
