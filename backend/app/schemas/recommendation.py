from pydantic import BaseModel, Field

from app.schemas.patient import PatientProfile


class RiskFlag(BaseModel):
    name: str
    severity: str
    evidence: str


class MedicationRecommendation(BaseModel):
    drug_class: str
    status: str
    rationale: str
    evidence: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class RecommendationRequest(BaseModel):
    patient: PatientProfile


class RecommendationResponse(BaseModel):
    case_id: str
    patient_summary: dict
    risk_flags: list[RiskFlag]
    recommendations: list[MedicationRecommendation]
    overall_status: str
    disclaimer: str
