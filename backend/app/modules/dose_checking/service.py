from app.schemas.medication_safety import MedicationSafetyWarning
from app.schemas.patient import PatientProfile


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
        category="dose_checking",
        severity=severity,
        target=target,
        message=message,
        evidence_ref=evidence_ref,
        related_medications=related_medications,
        related_observations=related_observations,
    )


def check_dose_safety(patient: PatientProfile) -> list[MedicationSafetyWarning]:
    medications = _medication_set(patient)
    warnings: list[MedicationSafetyWarning] = []

    if "digoxin" in medications and (patient.egfr is None or patient.egfr < 60):
        warnings.append(
            _warning(
                patient,
                "dose_digoxin_renal_review",
                "high" if patient.egfr is not None and patient.egfr < 30 else "moderate",
                "digoxin",
                "Digoxin dosing requires renal function review because reduced eGFR increases toxicity risk.",
                "week7_dose_rule:DIGOXIN_RENAL_REVIEW",
                ["digoxin"],
                {"egfr": patient.egfr},
            )
        )

    if medications.intersection({"spironolactone", "eplerenone", "finerenone"}) and (
        patient.egfr is None or patient.egfr < 30 or (patient.potassium is not None and patient.potassium >= 5.0)
    ):
        warnings.append(
            _warning(
                patient,
                "dose_mra_renal_potassium_review",
                "critical" if patient.potassium is not None and patient.potassium >= 5.5 else "high",
                "MRA",
                "MRA dose or continuation requires potassium and renal function review.",
                "week7_dose_rule:MRA_RENAL_K_REVIEW",
                sorted(medications.intersection({"spironolactone", "eplerenone", "finerenone"})),
                {"egfr": patient.egfr, "potassium": patient.potassium},
            )
        )

    if medications.intersection({"furosemide", "bumetanide", "torsemide"}):
        warnings.append(
            _warning(
                patient,
                "dose_loop_diuretic_lab_monitoring",
                "low",
                "loop_diuretic",
                "Loop diuretic therapy should include electrolyte, renal function, blood pressure, and volume status monitoring.",
                "week7_dose_rule:LOOP_DIURETIC_MONITORING",
                sorted(medications.intersection({"furosemide", "bumetanide", "torsemide"})),
                {
                    "egfr": patient.egfr,
                    "potassium": patient.potassium,
                    "systolic_bp": patient.systolic_bp,
                },
            )
        )

    if medications.intersection({"metoprolol", "bisoprolol", "carvedilol"}) and (
        patient.heart_rate is None or patient.heart_rate < 60
    ):
        warnings.append(
            _warning(
                patient,
                "dose_beta_blocker_hr_review",
                "moderate",
                "beta_blocker",
                "Beta-blocker dose escalation should be reviewed when heart rate is low or missing.",
                "week7_dose_rule:BETA_BLOCKER_HR_REVIEW",
                sorted(medications.intersection({"metoprolol", "bisoprolol", "carvedilol"})),
                {"heart_rate": patient.heart_rate},
            )
        )

    return warnings
