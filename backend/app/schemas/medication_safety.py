from pydantic import BaseModel, Field

from app.schemas.patient import PatientProfile


class MedicationSafetyWarning(BaseModel):
    warning_id: str
    case_id: str
    category: str
    severity: str
    target: str
    message: str
    evidence_ref: str
    related_medications: list[str] = Field(default_factory=list)
    related_observations: dict[str, float | str | None] = Field(default_factory=dict)


class MedicationSafetyRequest(BaseModel):
    patient: PatientProfile


class MedicationSafetyResponse(BaseModel):
    case_id: str
    warnings: list[MedicationSafetyWarning] = Field(default_factory=list)
