from typing import Any

from pydantic import BaseModel, Field

from app.schemas.clinical import Constraint
from app.schemas.dosing import SuggestedDosePlan
from app.schemas.medication_safety import MedicationSafetyWarning
from app.schemas.patient import PatientProfile


class RiskFlag(BaseModel):
    name: str
    severity: str
    evidence: str


class MedicationRecommendation(BaseModel):
    drug_class: str
    status: str
    rationale: str
    clinical_reasoning: list[str] = Field(default_factory=list)
    action_items: list[str] = Field(default_factory=list)
    monitoring: list[str] = Field(default_factory=list)
    evidence: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    constraint_ids: list[str] = Field(default_factory=list)
    safety_warning_ids: list[str] = Field(default_factory=list)


class RecommendationRequest(BaseModel):
    patient: PatientProfile
    clinical_state: dict[str, Any] | None = None


class RecommendationResponse(BaseModel):
    case_id: str
    patient_summary: dict
    risk_flags: list[RiskFlag]
    constraints: list[Constraint] = Field(default_factory=list)
    dose_warnings: list[MedicationSafetyWarning] = Field(default_factory=list)
    interaction_warnings: list[MedicationSafetyWarning] = Field(default_factory=list)
    dose_plans: list[SuggestedDosePlan] = Field(default_factory=list)
    dose_rules_version: str | None = None
    recommendations: list[MedicationRecommendation]
    overall_status: str
    disclaimer: str
