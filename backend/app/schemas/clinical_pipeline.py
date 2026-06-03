from typing import Any

from pydantic import BaseModel, Field

from app.schemas.clinical import Constraint
from app.schemas.patient import PatientProfile
from app.schemas.recommendation import RiskFlag


class NormalizedPatientProfile(BaseModel):
    case_id: str
    hf_type: str
    renal_status: str
    potassium_status: str
    bp_status: str
    hr_status: str
    has_polypharmacy: bool
    normalized_comorbidities: list[str] = Field(default_factory=list)
    normalized_current_medications: list[str] = Field(default_factory=list)
    normalized_allergies: list[str] = Field(default_factory=list)
    observations: dict[str, Any] = Field(default_factory=dict)


class PatientPayload(BaseModel):
    patient: PatientProfile


class NormalizationResponse(BaseModel):
    normalized_profile: NormalizedPatientProfile


class RiskExtractionResponse(BaseModel):
    normalized_profile: NormalizedPatientProfile
    risk_flags: list[RiskFlag]


class ConstraintResponse(BaseModel):
    normalized_profile: NormalizedPatientProfile
    risk_flags: list[RiskFlag]
    constraints: list[Constraint]
