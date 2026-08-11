from __future__ import annotations

import re
from typing import Any

from app.modules.clinical_intake_extraction.service import MEDICATIONS, normalize_text
from app.modules.explanation.question_focus import focus_class_ids_from_message, is_choice_question
from app.schemas.patient import PatientProfile


INTENT_PATTERNS = {
    "dose_adjustment": (
        "increase",
        "decrease",
        "uptitrate",
        "titrate",
        "dose",
        "tang lieu",
        "giam lieu",
        "chinh lieu",
    ),
    "start_medication": ("start", "initiate", "add", "bat dau", "them thuoc"),
    "stop_or_avoid": ("stop", "avoid", "hold", "ngung", "tranh", "tam dung"),
    "safety_check": ("safe", "contraindication", "warning", "an toan", "chong chi dinh"),
    "evidence_question": ("evidence", "guideline", "source", "citation", "bang chung", "khuyen cao"),
    "choice_question": ("hoac", "hay la", "lua chon", " or ", "either"),
    "follow_up_detail": (
        "giai thich them",
        "noi ro hon",
        "chi tiet hon",
        "cu the hon",
        "sau hon",
        "vi sao",
        "tai sao",
        "con gi nua",
        "elaborate",
        "explain more",
        "in detail",
        "more detail",
        "go deeper",
    ),
}


def _hf_type(patient: PatientProfile) -> str | None:
    if patient.heart_failure_profile.hf_type:
        return patient.heart_failure_profile.hf_type
    if patient.lvef is None:
        return None
    if patient.lvef <= 40:
        return "HFrEF"
    if patient.lvef < 50:
        return "HFmrEF"
    return "HFpEF"


def _active_classes(patient: PatientProfile) -> list[str]:
    classes = []
    for medication in patient.medications:
        if medication.status == "active" and medication.drug_class:
            classes.append(medication.drug_class)
    return sorted(set(classes))


def _mentioned_medications(message: str) -> list[dict[str, str]]:
    normalized = normalize_text(message)
    mentioned = []
    for canonical_name, (drug_class, aliases) in MEDICATIONS.items():
        if any(re.search(rf"(?<![a-z0-9]){re.escape(alias)}(?![a-z0-9])", normalized) for alias in aliases):
            mentioned.append({"name": canonical_name, "drug_class": drug_class})
    return mentioned


def _intent(message: str, *, has_prior_assistant: bool = False) -> str:
    normalized = normalize_text(message)
    if is_choice_question(message):
        return "choice_question"
    if has_prior_assistant:
        for term in INTENT_PATTERNS.get("follow_up_detail", ()):
            if term in normalized:
                return "follow_up_detail"
    for intent, terms in INTENT_PATTERNS.items():
        if intent in {"choice_question", "follow_up_detail"}:
            continue
        if any(term in normalized for term in terms):
            return intent
    return "recommendation"


def _safety_state(patient: PatientProfile) -> dict[str, Any]:
    return {
        "renal_risk": patient.egfr is not None and patient.egfr < 30,
        "hyperkalemia_risk": patient.potassium is not None and patient.potassium >= 5.0,
        "hypotension_risk": patient.systolic_bp is not None and patient.systolic_bp < 100,
        "bradycardia_risk": patient.heart_rate is not None and patient.heart_rate < 60,
        "red_flags": [flag.name for flag in patient.red_flags if flag.status == "present"],
    }


def build_clinical_state(
    patient: PatientProfile,
    message: str,
    *,
    has_prior_assistant: bool = False,
    last_assistant_message: str | None = None,
) -> dict[str, Any]:
    mentioned = _mentioned_medications(message)
    focus_classes = sorted({item["drug_class"] for item in mentioned})
    message_focus = focus_class_ids_from_message(message)
    if message_focus:
        focus_classes = sorted(set(focus_classes) | message_focus)
    if has_prior_assistant and last_assistant_message:
        prior_focus = focus_class_ids_from_message(last_assistant_message)
        if prior_focus:
            focus_classes = sorted(set(focus_classes) | prior_focus)
    if not focus_classes and patient.current_medications:
        focus_classes = _active_classes(patient)

    state = {
        "case_id": patient.case_id,
        "intent": _intent(message, has_prior_assistant=has_prior_assistant),
        "hf_type": _hf_type(patient),
        "key_values": {
            "lvef": patient.lvef,
            "egfr": patient.egfr,
            "potassium": patient.potassium,
            "systolic_bp": patient.systolic_bp,
            "heart_rate": patient.heart_rate,
            "age": patient.age,
            "sex": patient.sex,
            "weight_kg": patient.weight_kg,
            "creatinine": patient.creatinine,
        },
        "anticoagulation": {
            "inr": patient.inr,
            "inr_target_low": patient.inr_target_low,
            "inr_target_high": patient.inr_target_high,
            "acei_last_dose_hours_ago": patient.care_context.acei_last_dose_hours_ago,
        },
        "active_medication_classes": _active_classes(patient),
        "focus_medication_classes": focus_classes,
        "focus_class_ids": focus_classes,
        "mentioned_medications": mentioned,
        "conditions": patient.comorbidities,
        "allergies": patient.allergies,
        "safety_state": _safety_state(patient),
    }
    if last_assistant_message:
        state["last_assistant_excerpt"] = last_assistant_message[:4000]
    return state


def state_query_text(state: dict[str, Any]) -> str:
    values = state.get("key_values", {})
    pieces = [
        str(state.get("intent") or ""),
        str(state.get("hf_type") or ""),
        " ".join(state.get("focus_medication_classes") or []),
        " ".join(state.get("active_medication_classes") or []),
        " ".join(state.get("conditions") or []),
    ]
    for key, value in values.items():
        if value is not None:
            pieces.append(f"{key} {value}")
    for key, active in (state.get("safety_state") or {}).items():
        if active is True:
            pieces.append(key)
    return " ".join(piece for piece in pieces if piece).strip()
