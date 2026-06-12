from __future__ import annotations

import re
from typing import Any

from app.modules.clinical_intake_extraction.service import MEDICATIONS, normalize_text
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


def _intent(message: str) -> str:
    normalized = normalize_text(message)
    for intent, terms in INTENT_PATTERNS.items():
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


def build_clinical_state(patient: PatientProfile, message: str) -> dict[str, Any]:
    mentioned = _mentioned_medications(message)
    focus_classes = sorted({item["drug_class"] for item in mentioned})
    if not focus_classes and patient.current_medications:
        focus_classes = _active_classes(patient)

    return {
        "case_id": patient.case_id,
        "intent": _intent(message),
        "hf_type": _hf_type(patient),
        "key_values": {
            "lvef": patient.lvef,
            "egfr": patient.egfr,
            "potassium": patient.potassium,
            "systolic_bp": patient.systolic_bp,
            "heart_rate": patient.heart_rate,
        },
        "active_medication_classes": _active_classes(patient),
        "focus_medication_classes": focus_classes,
        "mentioned_medications": mentioned,
        "conditions": patient.comorbidities,
        "allergies": patient.allergies,
        "safety_state": _safety_state(patient),
    }


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
