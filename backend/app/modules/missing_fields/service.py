from collections.abc import Callable
from typing import Any

from app.modules.medication_presence import patient_on_acei, patient_on_warfarin
from app.schemas.chat import MissingField, MissingFieldCheck
from app.schemas.patient import PatientProfile


REQUIRED_CHAT_FIELDS: list[tuple[str, str, str, Callable[[PatientProfile], bool]]] = [
    ("lvef", "LVEF", "Needed to classify heart failure phenotype.", lambda patient: patient.lvef is not None),
    ("egfr", "eGFR", "Needed for renal dosing and GDMT eligibility checks.", lambda patient: patient.egfr is not None),
    (
        "potassium",
        "Serum potassium",
        "Needed for hyperkalemia-sensitive therapies such as MRA/RAAS inhibition.",
        lambda patient: patient.potassium is not None,
    ),
    (
        "systolic_bp",
        "Systolic blood pressure",
        "Needed to assess hypotension risk before GDMT titration.",
        lambda patient: patient.systolic_bp is not None,
    ),
    (
        "heart_rate",
        "Heart rate",
        "Needed to assess beta blocker safety and bradycardia risk.",
        lambda patient: patient.heart_rate is not None,
    ),
    (
        "current_medications",
        "Current medications",
        "Needed to detect drug interactions, duplicate therapy, and active GDMT.",
        lambda patient: bool(patient.current_medications),
    ),
    (
        "allergies",
        "Allergy history",
        "Needed to confirm medication allergy or document no known allergies.",
        lambda patient: bool(patient.allergies),
    ),
    (
        "care_context",
        "Care context",
        "Needed to understand the clinician question or treatment decision being considered.",
        lambda patient: bool(patient.care_context.clinician_question or patient.care_context.decision_context),
    ),
    (
        "red_flags",
        "Red flags",
        "Needed to screen urgent instability such as shock, active bleeding, or severe decompensation.",
        lambda patient: bool(patient.red_flags),
    ),
]


def _weight_present(patient: PatientProfile) -> bool:
    return patient.weight_kg is not None


DOSE_PERSONALIZATION_FIELDS: list[tuple[str, str, str, Callable[[PatientProfile], bool]]] = [
    ("weight_kg", "Body weight", "Needed for weight-based dosing and Cockcroft-Gault calculations.", _weight_present),
    ("sex", "Sex", "Needed for renal clearance and sex-specific dose-reduction rules.", lambda patient: bool(patient.sex)),
    ("age", "Age", "Needed for age-based dose reduction and renal clearance estimation.", lambda patient: patient.age is not None),
    (
        "creatinine",
        "Serum creatinine",
        "Needed for Cockcroft-Gault clearance and DOAC dose-reduction criteria.",
        lambda patient: patient.creatinine is not None,
    ),
]


WARFARIN_DOSE_FIELDS: list[tuple[str, str, str, Callable[[PatientProfile], bool]]] = [
    ("inr", "INR", "Needed to adjust warfarin dose against the therapeutic target.", lambda patient: patient.inr is not None),
]

ARNI_WASHOUT_FIELDS: list[tuple[str, str, str, Callable[[PatientProfile], bool]]] = [
    (
        "acei_last_dose_hours_ago",
        "ACEi last dose timing",
        "Needed to confirm the 36-hour ACEi washout before ARNI initiation.",
        lambda patient: patient.care_context.acei_last_dose_hours_ago is not None,
    ),
]


def _fields_for_intent(
    clinical_intent: str | None,
    *,
    patient: PatientProfile,
    clinical_state: dict[str, Any] | None = None,
) -> list[tuple[str, str, str, Callable[[PatientProfile], bool]]]:
    fields = list(REQUIRED_CHAT_FIELDS)
    if clinical_intent in {"dose_adjustment", "start_medication"}:
        fields.extend(DOSE_PERSONALIZATION_FIELDS)
    if patient_on_warfarin(patient) and clinical_intent in {"dose_adjustment", "safety_check"}:
        fields.extend(WARFARIN_DOSE_FIELDS)
    state = clinical_state or {}
    focus_text = " ".join(
        [
            *(state.get("focus_medication_classes") or []),
            *[item.get("name", "") for item in state.get("mentioned_medications") or []],
        ]
    ).lower()
    if patient_on_acei(patient) and any(token in focus_text for token in ("arni", "sacubitril", "entresto")):
        fields.extend(ARNI_WASHOUT_FIELDS)
    return fields


def check_missing_fields(
    patient: PatientProfile,
    *,
    clinical_intent: str | None = None,
    clinical_state: dict[str, Any] | None = None,
) -> MissingFieldCheck:
    missing: list[MissingField] = []
    present: list[str] = []
    for field, label, reason, predicate in _fields_for_intent(
        clinical_intent,
        patient=patient,
        clinical_state=clinical_state,
    ):
        if predicate(patient):
            present.append(field)
        else:
            missing.append(MissingField(field=field, label=label, reason=reason))

    return MissingFieldCheck(
        status="complete" if not missing else "missing_required_fields",
        missing_fields=missing,
        present_fields=present,
    )


def build_missing_fields_prompt(check: MissingFieldCheck) -> str:
    labels = [item.label for item in check.missing_fields[:6]]
    if not labels:
        return ""
    return (
        "Chua du thong tin de dua ra khuyen nghi thuoc an toan. "
        "Vui long bo sung: "
        + ", ".join(labels)
        + "."
    )
