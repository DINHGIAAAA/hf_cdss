from collections.abc import Callable

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


def check_missing_fields(patient: PatientProfile) -> MissingFieldCheck:
    missing: list[MissingField] = []
    present: list[str] = []
    for field, label, reason, predicate in REQUIRED_CHAT_FIELDS:
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
