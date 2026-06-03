from app.schemas.clinical_pipeline import NormalizedPatientProfile
from app.schemas.recommendation import RiskFlag


def extract_risks(profile: NormalizedPatientProfile) -> list[RiskFlag]:
    risks: list[RiskFlag] = []
    observations = profile.observations

    if profile.hf_type == "unknown":
        risks.append(
            RiskFlag(
                name="missing_lvef",
                severity="moderate",
                evidence="LVEF is missing; heart failure phenotype cannot be classified.",
            )
        )

    if profile.renal_status in {"severely_reduced", "kidney_failure"}:
        risks.append(
            RiskFlag(
                name="renal_impairment",
                severity="high",
                evidence=f"eGFR = {observations.get('egfr')}",
            )
        )
    elif profile.renal_status == "moderately_reduced":
        risks.append(
            RiskFlag(
                name="renal_impairment",
                severity="moderate",
                evidence=f"eGFR = {observations.get('egfr')}",
            )
        )

    if profile.potassium_status in {"elevated", "high"}:
        risks.append(
            RiskFlag(
                name="hyperkalemia",
                severity="high" if profile.potassium_status == "high" else "moderate",
                evidence=f"Potassium = {observations.get('potassium')}",
            )
        )

    if profile.bp_status in {"hypotension", "low"}:
        risks.append(
            RiskFlag(
                name="hypotension",
                severity="high" if profile.bp_status == "hypotension" else "moderate",
                evidence=f"SBP = {observations.get('systolic_bp')}",
            )
        )

    if profile.hr_status == "bradycardia":
        risks.append(
            RiskFlag(
                name="bradycardia",
                severity="moderate",
                evidence=f"Heart rate = {observations.get('heart_rate')}",
            )
        )

    if profile.has_polypharmacy:
        risks.append(
            RiskFlag(
                name="polypharmacy",
                severity="moderate",
                evidence="Current medication count >= 5.",
            )
        )

    if "diabetes" in profile.normalized_comorbidities:
        risks.append(
            RiskFlag(
                name="diabetes",
                severity="low",
                evidence="Diabetes listed in comorbidities.",
            )
        )

    if "ckd" in profile.normalized_comorbidities or "chronic kidney disease" in profile.normalized_comorbidities:
        if not any(risk.name == "renal_impairment" for risk in risks):
            risks.append(
                RiskFlag(
                    name="ckd_history",
                    severity="moderate",
                    evidence="CKD listed in comorbidities.",
                )
            )

    return risks
