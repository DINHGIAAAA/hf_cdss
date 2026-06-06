from app.schemas.medication_safety import MedicationSafetyWarning
from app.schemas.patient import PatientProfile


ACEI = {"lisinopril", "enalapril", "ramipril", "captopril"}
ARB = {"losartan", "valsartan", "candesartan"}
ARNI = {"sacubitril/valsartan", "entresto"}
MRA = {"spironolactone", "eplerenone", "finerenone"}
RAASI = ACEI | ARB | ARNI
NSAID = {"ibuprofen", "naproxen", "diclofenac", "celecoxib"}
ANTICOAGULANT = {"apixaban", "rivaroxaban", "warfarin", "dabigatran", "edoxaban"}
ANTIPLATELET = {"aspirin", "clopidogrel", "ticagrelor", "prasugrel"}


def _medication_set(patient: PatientProfile) -> set[str]:
    return {medication.strip().lower() for medication in patient.current_medications if medication.strip()}


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


def check_interactions(patient: PatientProfile) -> list[MedicationSafetyWarning]:
    medications = _medication_set(patient)
    warnings: list[MedicationSafetyWarning] = []

    if medications.intersection(ACEI) and medications.intersection(ARB):
        warnings.append(
            _warning(
                patient,
                "interaction_acei_arb_combination",
                "high",
                "RAAS_combination",
                "ACE inhibitor and ARB combination should generally be avoided because it increases renal and hyperkalemia risk.",
                "week7_interaction_rule:ACEI_ARB_AVOID_COMBINATION",
                sorted(medications.intersection(ACEI | ARB)),
                {"egfr": patient.egfr, "potassium": patient.potassium},
            )
        )

    if medications.intersection(RAASI) and medications.intersection(MRA):
        severity = "high" if patient.potassium is not None and patient.potassium >= 5.0 else "moderate"
        warnings.append(
            _warning(
                patient,
                "interaction_raasi_mra_hyperkalemia_monitoring",
                severity,
                "RAASi_MRA",
                "RAAS-inhibiting therapy combined with an MRA requires potassium and renal function monitoring.",
                "week7_interaction_rule:RAASI_MRA_K_RENAL_MONITORING",
                sorted(medications.intersection(RAASI | MRA)),
                {"egfr": patient.egfr, "potassium": patient.potassium},
            )
        )

    if medications.intersection(RAASI) and medications.intersection(NSAID):
        warnings.append(
            _warning(
                patient,
                "interaction_raasi_nsaid_renal_risk",
                "moderate",
                "RAASi_NSAID",
                "RAAS-inhibiting therapy with an NSAID may increase renal safety risk and should be reviewed.",
                "week7_interaction_rule:RAASI_NSAID_RENAL_REVIEW",
                sorted(medications.intersection(RAASI | NSAID)),
                {"egfr": patient.egfr},
            )
        )

    if medications.intersection(ANTICOAGULANT) and medications.intersection(ANTIPLATELET):
        warnings.append(
            _warning(
                patient,
                "interaction_anticoagulant_antiplatelet_bleeding",
                "moderate",
                "bleeding_risk",
                "Concurrent anticoagulant and antiplatelet therapy increases bleeding risk and should be reviewed.",
                "week7_interaction_rule:ANTICOAG_ANTIPLATELET_BLEEDING_REVIEW",
                sorted(medications.intersection(ANTICOAGULANT | ANTIPLATELET)),
                {},
            )
        )

    return warnings
