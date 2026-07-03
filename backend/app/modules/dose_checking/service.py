from app.modules.dose_safety.evaluator import evaluate_dose_safety_warnings
from app.modules.dose_safety.rule_loader import load_executable_dose_safety_warnings
from app.schemas.medication_safety import MedicationSafetyWarning
from app.schemas.patient import PatientProfile


def check_dose_safety(patient: PatientProfile) -> list[MedicationSafetyWarning]:
    return evaluate_dose_safety_warnings(patient, load_executable_dose_safety_warnings())
