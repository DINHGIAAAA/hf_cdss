from pydantic import BaseModel, Field


class PatientProfile(BaseModel):
    case_id: str = Field(examples=["CASE_001"])
    age: int | None = None
    sex: str | None = None
    lvef: float | None = Field(default=None, description="Left ventricular ejection fraction")
    egfr: float | None = None
    creatinine: float | None = None
    potassium: float | None = None
    systolic_bp: float | None = None
    heart_rate: float | None = None
    nyha_class: str | None = None
    comorbidities: list[str] = Field(default_factory=list)
    current_medications: list[str] = Field(default_factory=list)
    allergies: list[str] = Field(default_factory=list)
