"""Helpers to detect which medication classes a patient is currently on."""
from __future__ import annotations

from app.schemas.patient import PatientProfile


ACEI_KEYS = frozenset(
    {
        "enalapril",
        "enalapril maleate",
        "enalapril_maleate",
        "lisinopril",
        "ramipril",
        "captopril",
    }
)
ARB_KEYS = frozenset(
    {
        "valsartan",
        "losartan",
        "candesartan",
    }
)
ARNI_KEYS = frozenset(
    {
        "sacubitril/valsartan",
        "sacubitril valsartan",
        "sacubitril_and_valsartan",
        "sacubitril and valsartan",
        "entresto",
        "sacubitril_valsartan",
    }
)
WARFARIN_KEYS = frozenset({"warfarin", "warfarin sodium", "warfarin_sodium", "coumadin"})


def _normalize_drug_name(name: str) -> str:
    return name.strip().lower().replace("_", " ")


def _matches_any(name: str, keys: frozenset[str]) -> bool:
    normalized = _normalize_drug_name(name)
    return normalized in keys or any(key in normalized or normalized in key for key in keys)


def patient_medications(patient: PatientProfile) -> list[str]:
    return [
        *patient.current_medications,
        *[med.name for med in patient.medications if med.status == "active"],
    ]


def patient_on_acei(patient: PatientProfile) -> bool:
    return any(_matches_any(name, ACEI_KEYS) for name in patient_medications(patient))


def patient_on_arb(patient: PatientProfile) -> bool:
    return any(_matches_any(name, ARB_KEYS) for name in patient_medications(patient))


def patient_on_arni(patient: PatientProfile) -> bool:
    return any(_matches_any(name, ARNI_KEYS) for name in patient_medications(patient))


def patient_on_warfarin(patient: PatientProfile) -> bool:
    return any(_matches_any(name, WARFARIN_KEYS) for name in patient_medications(patient))


def acei_washout_hours_remaining(patient: PatientProfile) -> float | None:
    hours = patient.care_context.acei_last_dose_hours_ago
    if hours is None:
        return None
    return max(0.0, 36.0 - float(hours))
