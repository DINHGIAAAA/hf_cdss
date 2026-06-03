from app.schemas.recommendation import (
    MedicationRecommendation,
    RecommendationRequest,
    RecommendationResponse,
    RiskFlag,
)


DISCLAIMER = (
    "This recommendation is for clinical decision support only and must be "
    "reviewed by a licensed physician."
)


def build_recommendation(payload: RecommendationRequest) -> RecommendationResponse:
    patient = payload.patient
    risks: list[RiskFlag] = []

    if patient.egfr is not None and patient.egfr < 30:
        risks.append(
            RiskFlag(
                name="renal_impairment",
                severity="high",
                evidence=f"eGFR = {patient.egfr}",
            )
        )

    if patient.potassium is not None and patient.potassium >= 5.0:
        risks.append(
            RiskFlag(
                name="hyperkalemia",
                severity="high" if patient.potassium >= 5.5 else "moderate",
                evidence=f"Potassium = {patient.potassium}",
            )
        )

    recommendations = [
        MedicationRecommendation(
            drug_class="SGLT2 inhibitor",
            status="consider",
            rationale="Potential GDMT option pending physician review and contraindication checks.",
            evidence=["Guideline evidence placeholder"],
        )
    ]

    return RecommendationResponse(
        case_id=patient.case_id,
        patient_summary={
            "hf_type": "HFrEF" if patient.lvef is not None and patient.lvef <= 40 else "unclassified",
            "lvef": patient.lvef,
            "egfr": patient.egfr,
            "potassium": patient.potassium,
            "sbp": patient.systolic_bp,
            "heart_rate": patient.heart_rate,
            "comorbidities": patient.comorbidities,
        },
        risk_flags=risks,
        recommendations=recommendations,
        overall_status="approved_with_warnings" if risks else "approved",
        disclaimer=DISCLAIMER,
    )

