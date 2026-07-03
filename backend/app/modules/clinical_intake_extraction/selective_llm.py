"""Decide when clinical intake should call the LLM extractor."""

from __future__ import annotations

import re
from dataclasses import dataclass

from app.core.config import settings
from app.modules.clinical_intake_extraction.service import NEGATION_PREFIXES, extract_current_message, normalize_text
from app.modules.missing_fields.service import check_missing_fields
from app.schemas.patient import ClinicalValue, PatientProfile


SIMPLE_MISSING_FIELDS = frozenset(
    {
        "lvef",
        "egfr",
        "potassium",
        "systolic_bp",
        "heart_rate",
        "allergies",
        "red_flags",
        "current_medications",
    }
)

DECISION_KEYWORDS = (
    "should",
    "can",
    "recommend",
    "add",
    "start",
    "stop",
    "increase",
    "decrease",
    "safe",
    "contraindicated",
    "gdmt",
    "mra",
    "titrate",
    "switch",
    "continue",
    "evaluate",
    "assess",
    "danh gia",
    "co nen",
    "nen them",
    "nen tang",
    "nen giam",
    "ngung",
    "an toan",
    "thay the",
    "lieu",
    "dose",
)

CONTRAST_MARKERS = ("but", "however", "although", "though", "nhung", "tuy nhien", "mac du", "nhung ma")

MEDICATION_HINTS = (
    "mg",
    "mcg",
    "daily",
    "bid",
    "tid",
    "taking",
    "on ",
    "dung",
    "uong",
    "thuoc",
    "medication",
    "drug",
)


@dataclass(frozen=True)
class SelectiveLlmDecision:
    call_llm: bool
    reasons: list[str]


def _has_clinical_value(value: ClinicalValue | None) -> bool:
    return value is not None and value.value is not None


def _source_confidence(value: ClinicalValue | None) -> float | None:
    if not _has_clinical_value(value):
        return None
    if value.source and value.source.confidence is not None:
        return value.source.confidence
    return 0.9


def _named_item_confidence(items: list, *, default: float = 0.9) -> float | None:
    if not items:
        return None
    scores: list[float] = []
    for item in items:
        source = getattr(item, "source", None)
        if source and source.confidence is not None:
            scores.append(source.confidence)
        else:
            scores.append(default)
    return min(scores) if scores else None


def _field_confidence(patient: PatientProfile, field_id: str, aggregated_message: str) -> float | None:
    if field_id == "lvef":
        return _source_confidence(patient.heart_failure_profile.lvef)
    if field_id == "egfr":
        return _source_confidence(patient.labs.egfr)
    if field_id == "potassium":
        return _source_confidence(patient.labs.potassium)
    if field_id == "systolic_bp":
        return _source_confidence(patient.vitals.systolic_bp)
    if field_id == "heart_rate":
        return _source_confidence(patient.vitals.heart_rate)
    if field_id == "current_medications":
        return _named_item_confidence(patient.medications)
    if field_id == "allergies":
        return _named_item_confidence(patient.allergy_statements)
    if field_id == "red_flags":
        return _named_item_confidence(patient.red_flags)
    if field_id == "care_context":
        return _care_context_confidence(aggregated_message, patient)
    return None


def _care_context_clear(aggregated_message: str, patient: PatientProfile) -> bool:
    current = normalize_text(extract_current_message(aggregated_message))
    if patient.care_context.decision_context:
        return True
    if any(keyword in current for keyword in DECISION_KEYWORDS):
        return True
    raw_current = extract_current_message(aggregated_message)
    if "?" in raw_current:
        return True
    words = current.split()
    if 3 <= len(words) <= 16:
        return True
    if len(words) > 60 and not any(keyword in current for keyword in DECISION_KEYWORDS):
        return False
    return bool(patient.care_context.clinician_question or patient.care_context.decision_context)


def _care_context_confidence(aggregated_message: str, patient: PatientProfile) -> float:
    if _care_context_clear(aggregated_message, patient):
        return 0.88
    current = extract_current_message(aggregated_message).strip()
    question = (patient.care_context.clinician_question or "").strip()
    if question == aggregated_message.strip() or question == current:
        return 0.42
    return 0.62


def _message_complexity_high(aggregated_message: str) -> bool:
    current = normalize_text(extract_current_message(aggregated_message))
    negation_count = sum(
        1 for prefix in NEGATION_PREFIXES if re.search(rf"\b{re.escape(prefix)}\b", current)
    )
    contrast_count = sum(1 for marker in CONTRAST_MARKERS if re.search(rf"\b{re.escape(marker)}\b", current))
    word_count = len(current.split())
    threshold = settings.clinical_intake_selective_complexity_word_threshold

    if negation_count >= 2 and contrast_count >= 1:
        return True
    if negation_count >= 3:
        return True
    if word_count > threshold and (contrast_count >= 1 or negation_count >= 2):
        return True
    return False


def _regex_semantic_conflicts(regex_patient: PatientProfile, semantic_patient: PatientProfile | None) -> list[str]:
    if semantic_patient is None:
        return []

    reasons: list[str] = []
    regex_present_flags = {flag.name for flag in regex_patient.red_flags if flag.status == "present"}
    semantic_present_flags = {flag.name for flag in semantic_patient.red_flags if flag.status == "present"}
    regex_reports_stable = any(flag.status == "absent" for flag in regex_patient.red_flags)
    if regex_reports_stable and semantic_present_flags:
        reasons.append("red_flag_conflict")

    regex_meds = {med.name.lower() for med in regex_patient.medications}
    semantic_meds = {med.name.lower() for med in semantic_patient.medications}
    if regex_meds and semantic_meds and regex_meds.isdisjoint(semantic_meds):
        reasons.append("medication_source_conflict")

    if regex_present_flags and semantic_present_flags and regex_present_flags != semantic_present_flags:
        reasons.append("red_flag_mismatch")

    return reasons


def _low_confidence_present_fields(merged: PatientProfile, aggregated_message: str) -> list[str]:
    threshold = settings.clinical_intake_selective_min_confidence
    missing = check_missing_fields(merged)
    low_confidence: list[str] = []
    for field_id in missing.present_fields:
        confidence = _field_confidence(merged, field_id, aggregated_message)
        if confidence is not None and confidence < threshold:
            low_confidence.append(field_id)
    return low_confidence


def _missing_field_ids(patient: PatientProfile) -> list[str]:
    return [item.field for item in check_missing_fields(patient).missing_fields]


def _message_mentions_medications(aggregated_message: str) -> bool:
    current = normalize_text(extract_current_message(aggregated_message))
    return any(hint in current for hint in MEDICATION_HINTS)


def should_call_llm_extractor(
    *,
    aggregated_message: str,
    regex_patient: PatientProfile,
    semantic_patient: PatientProfile | None,
    merged: PatientProfile,
) -> SelectiveLlmDecision:
    if not settings.clinical_intake_selective_llm_enabled:
        if check_missing_fields(merged).status == "complete":
            return SelectiveLlmDecision(call_llm=False, reasons=["legacy_complete"])
        return SelectiveLlmDecision(call_llm=True, reasons=["legacy_incomplete"])

    missing = check_missing_fields(merged)
    reasons: list[str] = []
    conflicts = _regex_semantic_conflicts(regex_patient, semantic_patient)
    reasons.extend(conflicts)

    low_confidence = _low_confidence_present_fields(merged, aggregated_message)
    if low_confidence:
        reasons.append(f"low_confidence:{','.join(low_confidence)}")

    if "care_context" in missing.present_fields and not _care_context_clear(aggregated_message, merged):
        reasons.append("ambiguous_care_context")

    if _message_complexity_high(aggregated_message):
        reasons.append("complex_message")

    if missing.status == "complete":
        if reasons:
            return SelectiveLlmDecision(call_llm=True, reasons=reasons)
        return SelectiveLlmDecision(call_llm=False, reasons=["complete_high_confidence"])

    missing_ids = _missing_field_ids(merged)
    simple_missing = [field_id for field_id in missing_ids if field_id in SIMPLE_MISSING_FIELDS]
    complex_missing = [field_id for field_id in missing_ids if field_id not in SIMPLE_MISSING_FIELDS]

    if complex_missing:
        reasons.append(f"missing_complex:{','.join(complex_missing)}")

    if "current_medications" in missing_ids and _message_mentions_medications(aggregated_message):
        reasons.append("medication_extraction_gap")

    if missing_ids and len(missing_ids) >= 4 and len(extract_current_message(aggregated_message).split()) >= 20:
        reasons.append("broad_extraction_gap")

    if reasons:
        return SelectiveLlmDecision(call_llm=True, reasons=reasons)

    if simple_missing and len(simple_missing) <= settings.clinical_intake_selective_simple_missing_max:
        return SelectiveLlmDecision(call_llm=False, reasons=["simple_missing_fields_only"])

    return SelectiveLlmDecision(call_llm=True, reasons=["default_incomplete"])
