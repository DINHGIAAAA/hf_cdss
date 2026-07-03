from app.modules.drug_normalization.service import display_name_for_drug, resolve_pipeline_drug_id
from app.schemas.clinical_pipeline import NormalizedPatientProfile
from app.schemas.patient import PatientProfile


def _normalize_term(value: str) -> str:
    return " ".join(value.strip().lower().replace("_", " ").split())


def classify_hf_type(lvef: float | None) -> str:
    if lvef is None:
        return "unknown"
    if lvef <= 40:
        return "HFrEF"
    if lvef <= 49:
        return "HFmrEF"
    return "HFpEF"


def classify_renal_status(egfr: float | None) -> str:
    if egfr is None:
        return "missing"
    if egfr < 15:
        return "kidney_failure"
    if egfr < 30:
        return "severely_reduced"
    if egfr < 45:
        return "moderately_reduced"
    if egfr < 60:
        return "mildly_reduced"
    return "preserved"


def classify_potassium_status(potassium: float | None) -> str:
    if potassium is None:
        return "missing"
    if potassium < 3.5:
        return "low"
    if potassium < 5.0:
        return "normal"
    if potassium < 5.5:
        return "elevated"
    return "high"


def classify_bp_status(systolic_bp: float | None) -> str:
    if systolic_bp is None:
        return "missing"
    if systolic_bp < 90:
        return "hypotension"
    if systolic_bp < 100:
        return "low"
    if systolic_bp <= 130:
        return "acceptable"
    return "elevated"


def classify_hr_status(heart_rate: float | None) -> str:
    if heart_rate is None:
        return "missing"
    if heart_rate < 60:
        return "bradycardia"
    if heart_rate <= 100:
        return "acceptable"
    return "tachycardia"


def detect_polypharmacy(current_medications: list[str]) -> bool:
    return len(current_medications) >= 5


def normalize_patient(patient: PatientProfile) -> NormalizedPatientProfile:
    return NormalizedPatientProfile(
        case_id=patient.case_id,
        hf_type=classify_hf_type(patient.lvef),
        renal_status=classify_renal_status(patient.egfr),
        potassium_status=classify_potassium_status(patient.potassium),
        bp_status=classify_bp_status(patient.systolic_bp),
        hr_status=classify_hr_status(patient.heart_rate),
        has_polypharmacy=detect_polypharmacy(patient.current_medications),
        normalized_comorbidities=[_normalize_term(item) for item in patient.comorbidities],
        normalized_current_medications=[
            display_name_for_drug(resolve_pipeline_drug_id(item)) or _normalize_term(item)
            for item in patient.current_medications
        ],
        normalized_allergies=[_normalize_term(item) for item in patient.allergies],
        observations={
            "age": patient.age,
            "sex": patient.sex,
            "lvef": patient.lvef,
            "egfr": patient.egfr,
            "creatinine": patient.creatinine,
            "potassium": patient.potassium,
            "systolic_bp": patient.systolic_bp,
            "heart_rate": patient.heart_rate,
            "weight_kg": _weight_kg(patient),
            "inr": patient.inr,
            "nyha_class": patient.nyha_class,
        },
    )


def _weight_kg(patient: PatientProfile) -> float | None:
    value = patient.vitals.weight_kg.value if patient.vitals.weight_kg else None
    return float(value) if value is not None else None
