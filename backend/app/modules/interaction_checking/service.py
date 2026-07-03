from app.schemas.medication_safety import MedicationSafetyWarning
from app.schemas.patient import PatientProfile

from app.modules.interaction_checking.matcher import pair_matches, patient_medications
from app.modules.interaction_checking.rule_loader import load_executable_interaction_rules


def _warning(
    patient: PatientProfile,
    warning_id: str,
    severity: str,
    target: str,
    message: str,
    evidence_ref: str,
    related_medications: list[str],
    related_observations: dict[str, float | str | None],
) -> MedicationSafetyWarning:
    return MedicationSafetyWarning(
        warning_id=warning_id,
        case_id=patient.case_id,
        category="interaction_checking",
        severity=severity,
        target=target,
        message=message,
        evidence_ref=evidence_ref,
        related_medications=related_medications,
        related_observations=related_observations,
    )


def _apply_escalation(base_severity: str, rule_body: dict, patient: PatientProfile) -> str:
    severity = base_severity
    for item in rule_body.get("escalation") or []:
        field = item.get("field")
        operator = item.get("operator")
        threshold = item.get("value")
        candidate = item.get("severity") or severity
        value = getattr(patient, field, None)
        if value is None or threshold is None:
            continue
        try:
            numeric_value = float(value)
            numeric_threshold = float(threshold)
        except (TypeError, ValueError):
            continue
        matched = (
            (operator == "gte" and numeric_value >= numeric_threshold)
            or (operator == "gt" and numeric_value > numeric_threshold)
            or (operator == "lte" and numeric_value <= numeric_threshold)
            or (operator == "lt" and numeric_value < numeric_threshold)
        )
        if matched:
            severity = candidate
    return severity


def check_interactions(patient: PatientProfile) -> list[MedicationSafetyWarning]:
    medications = patient_medications(patient.current_medications)
    warnings: list[MedicationSafetyWarning] = []

    for rule in load_executable_interaction_rules():
        set_a = rule.get("drug_set_a") or []
        set_b = rule.get("drug_set_b") or []
        if not pair_matches(medications, set_a, set_b):
            continue

        body = rule.get("rule_body") or {}
        severity = _apply_escalation(str(rule.get("severity") or "moderate"), body, patient)
        target = body.get("target") or rule.get("target") or "general"
        message = body.get("message") or "Potential drug interaction detected."
        warning_id = f"interaction_{rule.get('interaction_rule_id') or rule.get('id')}"
        evidence_ref = rule.get("evidence_ref") or f"interaction_rule:{rule.get('interaction_rule_id')}"

        related = sorted(medications)
        warnings.append(
            _warning(
                patient,
                warning_id,
                severity,
                target,
                message,
                evidence_ref,
                related,
                {"egfr": patient.egfr, "potassium": patient.potassium},
            )
        )

    return warnings
