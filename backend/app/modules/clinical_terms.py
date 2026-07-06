"""Shared clinical term collection for retrieval and evidence filtering."""

from __future__ import annotations

import re
from typing import Any

from app.modules.drug_normalization.service import expand_drug_search_terms
from app.schemas.patient import PatientProfile

DRUG_CLASS_TERMS = {
    "mra": ["mra", "mineralocorticoid", "spironolactone", "eplerenone", "potassium", "hyperkalemia", "egfr"],
    "arni": ["arni", "sacubitril", "valsartan", "acei", "arb", "raas", "potassium", "hypotension", "egfr"],
    "acei": ["acei", "enalapril", "lisinopril", "raas", "potassium", "hypotension"],
    "arb": ["arb", "losartan", "valsartan", "candesartan", "raas", "potassium", "hypotension"],
    "beta_blocker": ["beta", "blocker", "metoprolol", "bisoprolol", "carvedilol", "bradycardia", "heart rate"],
    "sglt2i": ["sglt2", "dapagliflozin", "empagliflozin", "egfr", "renal", "kidney"],
}

CLINICAL_TERMS = {
    "ckd": ["ckd", "kidney", "renal", "egfr"],
    "diabetes": ["diabetes", "sglt2", "hypoglycemia"],
    "atrial fibrillation": ["atrial", "fibrillation", "apixaban", "warfarin", "bleeding"],
    "hypertension": ["hypertension", "blood pressure", "hypotension"],
    "copd": ["copd", "bronchospastic", "beta blocker"],
}

HF_BASELINE_TERMS = frozenset({"heart", "failure", "hfref", "gdmt"})


def tokenize_clinical_text(value: str) -> list[str]:
    return [token for token in re.split(r"[^a-z0-9+]+", value.lower()) if len(token) >= 3]


def add_terms_to_set(terms: set[str], values: list[str]) -> None:
    for value in values:
        terms.update(tokenize_clinical_text(value))


def dedupe_strings(values: list[str], *, max_items: int | None = None) -> list[str]:
    unique: list[str] = []
    seen: set[str] = set()
    for value in values:
        normalized = (value or "").strip()
        if not normalized:
            continue
        key = normalized.lower()
        if key in seen:
            continue
        seen.add(key)
        unique.append(normalized)
        if max_items is not None and len(unique) >= max_items:
            break
    return unique


def add_patient_medication_and_condition_terms(terms: set[str], patient: PatientProfile) -> None:
    add_terms_to_set(terms, patient.current_medications)
    add_terms_to_set(terms, patient.comorbidities)
    add_terms_to_set(terms, patient.allergies)

    for medication in patient.current_medications:
        add_terms_to_set(terms, expand_drug_search_terms(medication))
        medication_lower = medication.lower()
        for class_terms in DRUG_CLASS_TERMS.values():
            if any(term in medication_lower for term in class_terms):
                add_terms_to_set(terms, class_terms)

    for comorbidity in patient.comorbidities:
        lower = comorbidity.lower()
        for label, clinical_terms in CLINICAL_TERMS.items():
            if label in lower:
                add_terms_to_set(terms, clinical_terms)


def add_patient_measured_value_terms(terms: set[str], patient: PatientProfile) -> None:
    if patient.lvef is not None:
        add_terms_to_set(terms, ["lvef", "ejection fraction"])
        if patient.lvef <= 40:
            add_terms_to_set(terms, ["hfref", "reduced ejection fraction"])
        else:
            terms.add("hfpef")
    if patient.egfr is not None:
        add_terms_to_set(terms, ["egfr", "gfr", "renal"])
        if patient.egfr < 60:
            add_terms_to_set(terms, ["ckd", "kidney"])
    if patient.potassium is not None:
        terms.add("potassium")
        if patient.potassium >= 5.0:
            add_terms_to_set(terms, ["hyperkalemia", "k+"])
    if patient.systolic_bp is not None:
        add_terms_to_set(terms, ["systolic", "blood pressure", "hypotension"])
    if patient.heart_rate is not None:
        add_terms_to_set(terms, ["heart rate", "bradycardia"])
    if patient.creatinine is not None:
        terms.add("creatinine")
    if patient.inr is not None:
        terms.add("inr")


def add_patient_retrieval_expansion_terms(terms: set[str], patient: PatientProfile) -> None:
    if patient.lvef is not None and patient.lvef <= 40:
        add_terms_to_set(terms, ["hfref", "reduced ejection fraction", "gdmt", "arni", "mra", "sglt2", "beta blocker"])
    if patient.egfr is not None and patient.egfr < 60:
        add_terms_to_set(terms, ["renal", "kidney", "egfr", "ckd"])
    if patient.potassium is not None and patient.potassium >= 5.0:
        add_terms_to_set(terms, ["potassium", "hyperkalemia", "mra", "raas"])
    if patient.systolic_bp is not None and patient.systolic_bp < 100:
        add_terms_to_set(terms, ["hypotension", "blood pressure", "raas", "arni"])
    if patient.heart_rate is not None and patient.heart_rate < 60:
        add_terms_to_set(terms, ["bradycardia", "heart rate", "beta blocker"])


def patient_lab_context_text(patient: PatientProfile) -> str:
    parts: list[str] = []
    if patient.lvef is not None:
        parts.append(f"LVEF {patient.lvef}%")
    if patient.egfr is not None:
        parts.append(f"eGFR {patient.egfr}")
    if patient.potassium is not None:
        parts.append(f"potassium {patient.potassium}")
    if patient.systolic_bp is not None:
        parts.append(f"SBP {patient.systolic_bp}")
    if patient.heart_rate is not None:
        parts.append(f"HR {patient.heart_rate}")
    return " ".join(parts)


def patient_profile_entities(patient: PatientProfile) -> list[str]:
    """Patient-specific entities for negative filtering (excludes generic HF baselines)."""
    terms: set[str] = set()
    add_patient_medication_and_condition_terms(terms, patient)
    add_patient_measured_value_terms(terms, patient)
    return sorted(terms)


def collect_query_terms_for_patient(
    patient: PatientProfile,
    query: str | None = None,
    *,
    conversation_history: list[str] | None = None,
    clinical_state: dict[str, Any] | None = None,
    state_query_text_fn: Any | None = None,
) -> list[str]:
    terms: set[str] = set(HF_BASELINE_TERMS)

    if query:
        add_terms_to_set(terms, [query])

    if clinical_state:
        if state_query_text_fn is not None:
            add_terms_to_set(terms, [state_query_text_fn(clinical_state)])
        add_terms_to_set(terms, clinical_state.get("focus_medication_classes") or [])
        add_terms_to_set(terms, clinical_state.get("active_medication_classes") or [])
        add_terms_to_set(terms, clinical_state.get("conditions") or [])
        for medication in clinical_state.get("mentioned_medications") or []:
            if isinstance(medication, dict):
                add_terms_to_set(terms, [medication.get("name", ""), medication.get("drug_class", "")])

    if conversation_history:
        recent_turns = [turn.strip() for turn in conversation_history if turn and turn.strip()][-3:]
        if recent_turns:
            add_terms_to_set(terms, recent_turns)

    add_patient_medication_and_condition_terms(terms, patient)
    add_terms_to_set(
        terms,
        [
            patient.care_context.clinician_question or "",
            patient.care_context.decision_context or "",
            patient.care_context.treatment_goal or "",
        ],
    )
    add_patient_retrieval_expansion_terms(terms, patient)

    return sorted(terms)
