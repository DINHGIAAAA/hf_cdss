from typing import Any

from pydantic import BaseModel, Field


class DoseAmount(BaseModel):
    value: float
    unit: str
    frequency: str
    route: str = "oral"
    label: str | None = None


class DoseCalculationStep(BaseModel):
    description: str
    formula: str | None = None
    inputs: dict[str, Any] = Field(default_factory=dict)
    result: str


class SuggestedDosePlan(BaseModel):
    plan_id: str
    drug_name: str
    drug_class: str
    intent: str
    status: str
    rationale: str
    current_dose: DoseAmount | None = None
    recommended_dose: DoseAmount | None = None
    target_dose: DoseAmount | None = None
    titration_plan: list[str] = Field(default_factory=list)
    calculation_steps: list[DoseCalculationStep] = Field(default_factory=list)
    hold_criteria: list[str] = Field(default_factory=list)
    monitoring: list[str] = Field(default_factory=list)
    evidence_refs: list[str] = Field(default_factory=list)
    missing_inputs: list[str] = Field(default_factory=list)
    guideline_notes: list[str] = Field(default_factory=list)


class PatientDosingContext(BaseModel):
    case_id: str
    intent: str = "recommendation"
    hf_type: str | None = None
    age: int | None = None
    sex: str | None = None
    weight_kg: float | None = None
    egfr: float | None = None
    creatinine: float | None = None
    potassium: float | None = None
    systolic_bp: float | None = None
    heart_rate: float | None = None
    inr: float | None = None
    inr_target_low: float | None = None
    inr_target_high: float | None = None
    acei_last_dose_hours_ago: float | None = None
    focus_drug_classes: list[str] = Field(default_factory=list)
    focus_drugs: list[str] = Field(default_factory=list)
    current_medications: list[str] = Field(default_factory=list)
