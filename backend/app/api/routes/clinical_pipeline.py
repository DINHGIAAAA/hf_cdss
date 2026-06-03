from fastapi import APIRouter

from app.modules.clinical_normalization.service import normalize_patient
from app.modules.constraint_builder.service import build_constraints
from app.modules.risk_extraction.service import extract_risks
from app.schemas.clinical_pipeline import (
    ConstraintResponse,
    NormalizationResponse,
    PatientPayload,
    RiskExtractionResponse,
)


router = APIRouter()


@router.post("/normalize", response_model=NormalizationResponse)
def normalize(payload: PatientPayload) -> NormalizationResponse:
    return NormalizationResponse(normalized_profile=normalize_patient(payload.patient))


@router.post("/risks", response_model=RiskExtractionResponse)
def risks(payload: PatientPayload) -> RiskExtractionResponse:
    profile = normalize_patient(payload.patient)
    risk_flags = extract_risks(profile)
    return RiskExtractionResponse(normalized_profile=profile, risk_flags=risk_flags)


@router.post("/constraints", response_model=ConstraintResponse)
def constraints(payload: PatientPayload) -> ConstraintResponse:
    profile = normalize_patient(payload.patient)
    risk_flags = extract_risks(profile)
    clinical_constraints = build_constraints(profile, risk_flags)
    return ConstraintResponse(
        normalized_profile=profile,
        risk_flags=risk_flags,
        constraints=clinical_constraints,
    )
