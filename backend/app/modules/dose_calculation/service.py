"""Dose calculation service - main entry point for dose calculations from FDA labels."""
from __future__ import annotations

import re
from typing import Any

from app.schemas.dosing import SuggestedDosePlan
from app.schemas.patient import PatientProfile
from app.modules.dose_calculation.evaluator import calculate_dose, calculate_doses_for_patient
from app.modules.dose_calculation.rule_loader import (
    get_drug_by_key,
    list_available_drugs,
    load_dose_tables,
)
from app.modules.chat.clinical_intent import should_compute_dose_plans
from app.modules.medication_presence import patient_on_acei, patient_on_arni
from app.modules.graphrag.query_decomposition import normalize_drug_class
from app.modules.recommendation.drug_class_keys import CANONICAL_GDMT_CLASS_IDS


DOSE_SOURCE_VERSION = "fda_xml_labels"


def calculate_single_dose(
    patient: PatientProfile,
    drug_key: str,
    intent: str = "recommendation",
) -> SuggestedDosePlan | None:
    """Calculate dose for a single drug from FDA label tables."""
    return calculate_dose(patient, drug_key, intent)


def calculate_multiple_doses(
    patient: PatientProfile,
    drug_keys: list[str] | None = None,
) -> list[SuggestedDosePlan]:
    """Calculate doses for multiple drugs (or all label drugs if keys omitted)."""
    return calculate_doses_for_patient(patient, drug_keys)


def get_available_drugs() -> list[dict]:
    """Get list of all drugs with dose tables derived from FDA XML labels."""
    return list_available_drugs()


def get_drug_info(drug_key: str) -> dict | None:
    """Get detailed information for a specific drug."""
    return get_drug_by_key(drug_key)


def dose_source_version() -> str:
    """Version string for recommendation traceability."""
    tables = load_dose_tables()
    return str(tables.get("version") or DOSE_SOURCE_VERSION)


def invalidate_dose_label_cache() -> None:
    """Clear cached dose tables (Postgres + XML)."""
    from app.modules.dose_calculation.rule_loader import invalidate_dose_tables_cache

    invalidate_dose_tables_cache()


def _strip_dose_text(name: str) -> str:
    cleaned = re.sub(r"\b\d+(?:[.,]\d+)?\s*(?:mg|mcg|g|µg|ug)\b", " ", name, flags=re.I)
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" -,/()")
    return cleaned


def resolve_drug_key(name: str) -> str | None:
    """Map a free-text medication name to a dose_calculation drug_key."""
    from app.modules.dose_calculation.convert_extracted_doses import normalize_drug_name

    if not name or not str(name).strip():
        return None
    cleaned = _strip_dose_text(str(name))
    key = normalize_drug_name(cleaned)
    if get_drug_by_key(key):
        return key
    # Fallback: match available keys contained in the name
    lowered = cleaned.lower().replace("-", " ")
    for drug in list_available_drugs():
        dk = str(drug.get("drug_key") or "")
        token = dk.replace("_", " ")
        if token and (token in lowered or lowered in token):
            return dk
        generic = str(drug.get("generic_name") or "").lower()
        if generic and generic in lowered:
            return dk
    return None


def _class_matches(drug_class: str, needle: str) -> bool:
    left = (drug_class or "").lower()
    right = (needle or "").lower()
    if not left or not right:
        return False
    aliases = {
        "acei": "ace inhibitor",
        "ace inhibitor": "ace inhibitor",
        "arb": "arb",
        "arni": "arni",
        "mra": "mra",
        "beta blocker": "beta blocker",
        "beta-blocker": "beta blocker",
        "sglt2": "sglt2 inhibitor",
        "sglt2 inhibitor": "sglt2 inhibitor",
        "loop diuretic": "loop diuretic",
        "anticoagulant": "anticoagulant",
    }
    left_n = aliases.get(left, left)
    right_n = aliases.get(right, right)
    return left_n == right_n or left_n in right_n or right_n in left_n


def _candidate_drug_keys(
    patient: PatientProfile,
    clinical_state: dict[str, Any] | None,
    recommendation: Any | None,
) -> list[str]:
    state = clinical_state or {}
    names: list[str] = []
    names.extend(str(x) for x in (state.get("focus_drugs") or []) if x)
    names.extend(
        str(item.get("name"))
        for item in (state.get("mentioned_medications") or [])
        if isinstance(item, dict) and item.get("name")
    )
    names.extend(patient.current_medications or [])

    keys: list[str] = []
    for name in names:
        key = resolve_drug_key(name)
        if key:
            keys.append(key)

    focus_classes = [str(c) for c in (state.get("focus_medication_classes") or []) if c]
    intent = str(state.get("intent") or "recommendation")
    has_explicit_focus = bool(
        state.get("focus_drugs")
        or state.get("mentioned_medications")
        or state.get("focus_medication_classes")
    )
    if recommendation is not None and intent == "dose_adjustment" and not has_explicit_focus:
        for item in getattr(recommendation, "recommendations", []) or []:
            if getattr(item, "status", None) in {"consider", "consider_with_caution", "review"}:
                focus_classes.append(str(getattr(item, "drug_class", "") or ""))

    if focus_classes:
        for fc in focus_classes:
            for drug in list_available_drugs():
                dk = drug.get("drug_key")
                dclass = str(drug.get("drug_class") or "")
                if not dk:
                    continue
                if _class_matches(dclass, fc):
                    keys.append(str(dk))
                    break

    return _dedupe_keys_one_per_class(list(dict.fromkeys(keys)), patient)


def _canonical_class_for_drug_key(drug_key: str) -> str:
    drug = get_drug_by_key(drug_key)
    if not drug:
        return ""
    raw = str(drug.get("drug_class") or "")
    normalized = normalize_drug_class(raw.replace("ACE INHIBITOR", "ace inhibitor"))
    if normalized in CANONICAL_GDMT_CLASS_IDS:
        return normalized
    if "ace inhibitor" in raw.lower() or raw.upper() == "ACE INHIBITOR":
        return "acei_arb"
    if raw.upper() == "ARB":
        return "arb"
    return normalized


def _dedupe_keys_one_per_class(keys: list[str], patient: PatientProfile) -> list[str]:
    patient_keys: list[str] = []
    for name in patient.current_medications or []:
        key = resolve_drug_key(name)
        if key:
            patient_keys.append(key)

    chosen: dict[str, str] = {}
    for key in keys:
        class_id = _canonical_class_for_drug_key(key)
        bucket = class_id or f"__other_{key}"
        if bucket not in chosen:
            chosen[bucket] = key
        elif key in patient_keys:
            chosen[bucket] = key
    return list(chosen.values())


def _skip_drug_for_patient(drug_key: str, patient: PatientProfile) -> bool:
    drug = get_drug_by_key(drug_key)
    if not drug:
        return True
    drug_class = str(drug.get("drug_class") or "").upper()
    # If already on ARNI, skip recommending concurrent ACEI/ARB label doses
    if patient_on_arni(patient) and drug_class in {"ACE INHIBITOR", "ARB"} and not patient_on_acei(patient):
        return True
    return False


def build_dose_plans(
    patient: PatientProfile,
    *,
    clinical_state: dict[str, Any] | None = None,
    recommendation: Any | None = None,
) -> list[SuggestedDosePlan]:
    """Build dose plans from FDA drug labels for relevant candidate drugs."""
    state = clinical_state or {}
    intent = str(state.get("intent") or "recommendation")
    if not should_compute_dose_plans(intent):
        return []

    plans: list[SuggestedDosePlan] = []
    seen: set[str] = set()
    for drug_key in _candidate_drug_keys(patient, clinical_state, recommendation):
        if drug_key in seen:
            continue
        if _skip_drug_for_patient(drug_key, patient):
            continue
        seen.add(drug_key)
        plan = calculate_dose(patient, drug_key, intent)
        if plan is not None:
            plans.append(plan)
    return plans
