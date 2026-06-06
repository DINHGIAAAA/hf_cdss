from typing import Any

from pydantic import BaseModel, Field


class Medication(BaseModel):
    medication_id: str
    name: str
    drug_class: str
    route: str | None = None
    typical_starting_dose: str | None = None
    contraindications: list[str] = Field(default_factory=list)
    monitoring_requirements: list[str] = Field(default_factory=list)


class Observation(BaseModel):
    observation_id: str
    case_id: str
    name: str
    value: float | str
    unit: str | None = None
    observed_at: str | None = None


class Diagnosis(BaseModel):
    diagnosis_id: str
    case_id: str
    name: str
    category: str | None = None
    evidence: str | None = None


class Constraint(BaseModel):
    constraint_id: str
    case_id: str
    target_drug_class: str
    action: str
    reason: str
    constraint_type: str | None = None
    evidence_ref: str | None = None


class Evidence(BaseModel):
    evidence_id: str
    source_type: str
    title: str
    excerpt: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class AuditLog(BaseModel):
    audit_id: str
    case_id: str
    input: dict[str, Any]
    context: dict[str, Any]
    output: dict[str, Any]
    agent_results: list[dict[str, Any]] = Field(default_factory=list)
    created_at: str
