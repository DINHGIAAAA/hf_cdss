from pydantic import BaseModel, Field


class LabGateCheck(BaseModel):
    lab: str
    label: str
    value: str | None = None
    requirement: str
    passed: bool | None = None


class MedicationPathwayStep(BaseModel):
    step_order: int
    class_id: str
    drug_class: str
    pathway_phase: str = Field(
        description="active | next | hold | blocked — position on the GDMT roadmap",
    )
    recommendation_status: str
    patient_drug: str | None = None
    dose_summary: str | None = None
    action: str = ""
    lab_gates: list[LabGateCheck] = Field(default_factory=list)
