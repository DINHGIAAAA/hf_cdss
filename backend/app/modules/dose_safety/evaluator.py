"""Evaluate dose safety warning rules against a patient profile."""

from __future__ import annotations

from typing import Any

from app.modules.drug_normalization.service import normalize_drug_name
from app.schemas.medication_safety import MedicationSafetyWarning
from app.schemas.patient import PatientProfile


def _normalize_medication(value: str) -> str | None:
    normalized = normalize_drug_name(value)
    if normalized:
        return normalized.replace(" ", "_").lower()
    token = (value or "").strip().lower().replace(" ", "_")
    return token or None


def patient_medications(patient: PatientProfile) -> set[str]:
    meds: set[str] = set()
    for item in patient.current_medications:
        normalized = _normalize_medication(item)
        if normalized:
            meds.add(normalized)
    return meds


def _med_matches_key(medications: set[str], drug_key: str) -> bool:
    key = drug_key.strip().lower().replace(" ", "_")
    for med in medications:
        if med == key or key in med or med in key:
            return True
    return False


def matched_medications(medications: set[str], drug_keys: list[str]) -> list[str]:
    return sorted({med for med in medications for key in drug_keys if _med_matches_key({med}, key)})


def medications_match(medications: set[str], drug_keys: list[str]) -> bool:
    return any(_med_matches_key(medications, key) for key in drug_keys)


def _field_value(patient: PatientProfile, field: str) -> float | str | None:
    if field == "systolic_bp":
        return patient.systolic_bp
    return getattr(patient, field, None)


def _evaluate_condition(patient: PatientProfile, condition: dict[str, Any]) -> bool:
    operator = condition.get("operator")
    if operator == "always":
        return True

    field = condition.get("field")
    if not field:
        return False

    value = _field_value(patient, field)
    threshold = condition.get("value")

    if operator == "missing":
        return value is None
    if operator == "present":
        return value is not None
    if operator == "missing_or_lt":
        return value is None or (threshold is not None and float(value) < float(threshold))
    if operator == "missing_or_lte":
        return value is None or (threshold is not None and float(value) <= float(threshold))
    if value is None or threshold is None:
        return False

    numeric_value = float(value)
    numeric_threshold = float(threshold)
    if operator == "lt":
        return numeric_value < numeric_threshold
    if operator == "lte":
        return numeric_value <= numeric_threshold
    if operator == "gt":
        return numeric_value > numeric_threshold
    if operator == "gte":
        return numeric_value >= numeric_threshold
    return False


def _trigger_matches(patient: PatientProfile, trigger: dict[str, Any]) -> bool:
    groups = trigger.get("condition_groups") or [[]]
    if not groups:
        return True
    return any(all(_evaluate_condition(patient, cond) for cond in group) for group in groups)


def _resolve_severity(patient: PatientProfile, rule: dict[str, Any]) -> str:
    body = rule.get("rule_body") or {}
    severity = str(rule.get("default_severity") or body.get("default_severity") or "moderate")
    for item in body.get("severity_rules") or []:
        if _evaluate_condition(patient, item):
            severity = str(item.get("severity") or severity)
    return severity


def _related_observations(patient: PatientProfile, fields: list[str]) -> dict[str, float | str | None]:
    return {field: _field_value(patient, field) for field in fields}


def evaluate_dose_safety_warning(
    patient: PatientProfile,
    rule: dict[str, Any],
    medications: set[str] | None = None,
) -> MedicationSafetyWarning | None:
    meds = medications if medications is not None else patient_medications(patient)
    drug_keys = list(rule.get("drug_keys") or [])
    if not drug_keys or not medications_match(meds, drug_keys):
        return None

    body = rule.get("rule_body") or {}
    trigger = body.get("trigger") or {}
    if not _trigger_matches(patient, trigger):
        return None

    warning_id = str(rule.get("dose_safety_warning_id") or rule.get("warning_id") or "")
    related_meds = matched_medications(meds, drug_keys)
    observation_fields = list(body.get("related_observation_fields") or [])

    return MedicationSafetyWarning(
        warning_id=warning_id,
        case_id=patient.case_id,
        category="dose_checking",
        severity=_resolve_severity(patient, rule),
        target=str(rule.get("target") or "general"),
        message=str(body.get("message") or "Dose safety review recommended."),
        evidence_ref=rule.get("evidence_ref") or f"dose_safety_warning:{warning_id}",
        related_medications=related_meds,
        related_observations=_related_observations(patient, observation_fields),
    )


def evaluate_dose_safety_warnings(
    patient: PatientProfile,
    rules: list[dict[str, Any]],
) -> list[MedicationSafetyWarning]:
    medications = patient_medications(patient)
    warnings: list[MedicationSafetyWarning] = []
    for rule in rules:
        warning = evaluate_dose_safety_warning(patient, rule, medications)
        if warning:
            warnings.append(warning)
    return warnings
