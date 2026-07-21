from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator


class SourceTrace(BaseModel):
    source_type: str | None = None
    document_id: str | None = None
    page: int | None = None
    source_text: str | None = None
    confidence: float | None = Field(default=None, ge=0, le=1)


class ClinicalValue(BaseModel):
    value: float | str | bool | None = None
    unit: str | None = None
    measured_at: datetime | None = None
    source: SourceTrace | None = None


class PatientIdentity(BaseModel):
    case_id: str = Field(examples=["CASE_001"])
    patient_id: str | None = None
    external_patient_id: str | None = None
    medical_record_number: str | None = None
    full_name: str | None = None
    preferred_name: str | None = None


class EncounterContext(BaseModel):
    encounter_id: str | None = None
    encounter_type: str | None = None
    encounter_status: str = "active"
    department: str | None = None
    primary_reason: str | None = None
    started_at: datetime | None = None
    ended_at: datetime | None = None


class Demographics(BaseModel):
    date_of_birth: date | None = None
    age: int | None = Field(default=None, ge=0, le=130)
    sex: str | None = None
    sex_at_birth: str | None = None
    gender_identity: str | None = None
    blood_type: str | None = None
    rh_factor: str | None = None
    ethnicity: str | None = None
    preferred_language: str | None = None


class ChiefComplaint(BaseModel):
    text: str | None = None
    duration: str | None = None
    severity: str | None = None
    source: SourceTrace | None = None


class Symptom(BaseModel):
    name: str
    status: str = "present"
    severity: str | None = None
    onset: str | None = None
    duration: str | None = None
    source: SourceTrace | None = None


class Vitals(BaseModel):
    systolic_bp: ClinicalValue | None = None
    diastolic_bp: ClinicalValue | None = None
    heart_rate: ClinicalValue | None = None
    respiratory_rate: ClinicalValue | None = None
    spo2: ClinicalValue | None = None
    weight_kg: ClinicalValue | None = None
    height_cm: ClinicalValue | None = None


class PhysicalExam(BaseModel):
    volume_status: str | None = None
    peripheral_edema: str | None = None
    lung_crackles: str | None = None
    jugular_venous_distension: str | None = None
    murmur: str | None = None
    source: SourceTrace | None = None


class HeartFailureProfile(BaseModel):
    lvef: ClinicalValue | None = None
    hf_type: str | None = None
    nyha_class: str | None = None
    acute_decompensated: bool | None = None
    cardiogenic_shock: bool | None = None
    source: SourceTrace | None = None


class Labs(BaseModel):
    egfr: ClinicalValue | None = None
    creatinine: ClinicalValue | None = None
    potassium: ClinicalValue | None = None
    sodium: ClinicalValue | None = None
    hemoglobin: ClinicalValue | None = None
    hba1c: ClinicalValue | None = None
    alt: ClinicalValue | None = None
    ast: ClinicalValue | None = None
    inr: ClinicalValue | None = None


class Biomarkers(BaseModel):
    bnp: ClinicalValue | None = None
    nt_probnp: ClinicalValue | None = None
    troponin: ClinicalValue | None = None


class EcgReport(BaseModel):
    rhythm: str | None = None
    qrs_duration_ms: float | None = None
    qt_interval_ms: float | None = None
    av_block: str | None = None
    source: SourceTrace | None = None


class EchocardiographyReport(BaseModel):
    lvef: ClinicalValue | None = None
    lv_dilation: str | None = None
    rv_function: str | None = None
    valve_disease: str | None = None
    pulmonary_pressure: ClinicalValue | None = None
    source: SourceTrace | None = None


class ImagingReport(BaseModel):
    modality: str
    finding: str | None = None
    impression: str | None = None
    source: SourceTrace | None = None


class Condition(BaseModel):
    name: str
    normalized_name: str | None = None
    category: str | None = None
    status: str = "active"
    onset_date: date | None = None
    source: SourceTrace | None = None


class RiskFactor(BaseModel):
    name: str
    status: str = "present"
    source: SourceTrace | None = None


class MedicationStatement(BaseModel):
    name: str
    normalized_name: str | None = None
    drug_class: str | None = None
    dose_value: float | None = None
    dose_unit: str | None = None
    route: str | None = None
    frequency: str | None = None
    status: str = "active"
    source: SourceTrace | None = None


class AllergyStatement(BaseModel):
    substance: str
    normalized_substance: str | None = None
    reaction: str | None = None
    severity: str | None = None
    status: str = "active"
    source: SourceTrace | None = None


class ContraindicationHistory(BaseModel):
    prior_angioedema: bool | None = None
    pregnancy: bool | None = None
    lactation: bool | None = None
    dialysis: bool | None = None
    active_bleeding: bool | None = None
    av_block: bool | None = None
    sick_sinus_syndrome: bool | None = None
    source: SourceTrace | None = None


class ProcedureDevice(BaseModel):
    name: str
    device_type: str | None = None
    implanted_at: date | None = None
    status: str = "active"
    source: SourceTrace | None = None


class FamilyHistory(BaseModel):
    condition: str
    relation: str | None = None
    age_at_onset: int | None = None
    source: SourceTrace | None = None


class Lifestyle(BaseModel):
    smoking_status: str | None = None
    alcohol_use: str | None = None
    substance_use: str | None = None
    exercise_tolerance: str | None = None
    diet_notes: str | None = None


class PregnancyReproductive(BaseModel):
    pregnancy_capable: bool | None = None
    is_pregnant: bool | None = None
    is_lactating: bool | None = None
    last_menstrual_period: date | None = None


class CareContext(BaseModel):
    care_setting: str | None = None
    clinician_question: str | None = None
    treatment_goal: str | None = None
    decision_context: str | None = None
    acei_last_dose_hours_ago: float | None = None
    inr_target_low: float | None = None
    inr_target_high: float | None = None


class RedFlag(BaseModel):
    name: str
    status: str = "present"
    severity: str | None = None
    source: SourceTrace | None = None


class DataQuality(BaseModel):
    missing_fields: list[str] = Field(default_factory=list)
    low_confidence_fields: list[str] = Field(default_factory=list)
    validation_warnings: list[str] = Field(default_factory=list)
    last_checked_at: datetime | None = None


class ClinicalDocument(BaseModel):
    document_id: str | None = None
    file_name: str | None = None
    file_type: str | None = None
    storage_uri: str | None = None
    processing_status: str | None = None


def _value(item: ClinicalValue | None) -> Any:
    return item.value if item is not None else None


def _clinical_value(value: Any, unit: str | None = None) -> ClinicalValue | None:
    if value is None:
        return None
    if isinstance(value, dict):
        return ClinicalValue(**value)
    return ClinicalValue(value=value, unit=unit)


class PatientProfile(BaseModel):
    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    patient_identity: PatientIdentity
    encounter: EncounterContext = Field(default_factory=EncounterContext)
    demographics: Demographics = Field(default_factory=Demographics)
    chief_complaint: ChiefComplaint | None = None
    symptoms: list[Symptom] = Field(default_factory=list)
    vitals: Vitals = Field(default_factory=Vitals)
    physical_exam: PhysicalExam | None = None
    heart_failure_profile: HeartFailureProfile = Field(default_factory=HeartFailureProfile)
    labs: Labs = Field(default_factory=Labs)
    biomarkers: Biomarkers = Field(default_factory=Biomarkers)
    ecg: EcgReport | None = None
    echocardiography: EchocardiographyReport | None = None
    imaging: list[ImagingReport] = Field(default_factory=list)
    conditions: list[Condition] = Field(default_factory=list)
    risk_factors: list[RiskFactor] = Field(default_factory=list)
    medications: list[MedicationStatement] = Field(default_factory=list)
    allergy_statements: list[AllergyStatement] = Field(default_factory=list)
    contraindication_history: ContraindicationHistory = Field(default_factory=ContraindicationHistory)
    procedures_devices: list[ProcedureDevice] = Field(default_factory=list)
    family_history: list[FamilyHistory] = Field(default_factory=list)
    lifestyle: Lifestyle = Field(default_factory=Lifestyle)
    pregnancy_reproductive: PregnancyReproductive = Field(default_factory=PregnancyReproductive)
    care_context: CareContext = Field(default_factory=CareContext)
    red_flags: list[RedFlag] = Field(default_factory=list)
    data_quality: DataQuality = Field(default_factory=DataQuality)
    clinical_documents: list[ClinicalDocument] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def accept_legacy_flat_payload(cls, data: Any) -> Any:
        if not isinstance(data, dict) or "patient_identity" in data:
            return data

        output = dict(data)
        case_id = output.pop("case_id", None)
        age = output.pop("age", None)
        sex = output.pop("sex", None)
        lvef = output.pop("lvef", None)
        egfr = output.pop("egfr", None)
        creatinine = output.pop("creatinine", None)
        potassium = output.pop("potassium", None)
        systolic_bp = output.pop("systolic_bp", None)
        heart_rate = output.pop("heart_rate", None)
        weight_kg = output.pop("weight_kg", None)
        nyha_class = output.pop("nyha_class", None)
        comorbidities = output.pop("comorbidities", [])
        current_medications = output.pop("current_medications", [])
        allergies = output.pop("allergies", [])

        output["patient_identity"] = {
            **output.get("patient_identity", {}),
            "case_id": case_id,
        }
        output["demographics"] = {
            **output.get("demographics", {}),
            "age": age,
            "sex": sex,
        }
        output["vitals"] = {
            **output.get("vitals", {}),
            "systolic_bp": _clinical_value(systolic_bp, "mmHg"),
            "heart_rate": _clinical_value(heart_rate, "bpm"),
            "weight_kg": _clinical_value(weight_kg, "kg"),
        }
        output["heart_failure_profile"] = {
            **output.get("heart_failure_profile", {}),
            "lvef": _clinical_value(lvef, "%"),
            "nyha_class": nyha_class,
        }
        output["labs"] = {
            **output.get("labs", {}),
            "egfr": _clinical_value(egfr, "mL/min/1.73m2"),
            "creatinine": _clinical_value(creatinine),
            "potassium": _clinical_value(potassium, "mmol/L"),
        }
        output["conditions"] = [
            item if isinstance(item, dict) else {"name": str(item), "status": "active"}
            for item in comorbidities
        ]
        output["medications"] = [
            item if isinstance(item, dict) else {"name": str(item), "status": "active"}
            for item in current_medications
        ]
        output["allergy_statements"] = [
            item if isinstance(item, dict) else {"substance": str(item), "status": "active"}
            for item in allergies
        ]
        return output

    @property
    def case_id(self) -> str:
        return self.patient_identity.case_id

    @property
    def age(self) -> int | None:
        return self.demographics.age

    @property
    def sex(self) -> str | None:
        return self.demographics.sex or self.demographics.sex_at_birth

    @property
    def lvef(self) -> float | None:
        value = _value(self.heart_failure_profile.lvef) or _value(
            self.echocardiography.lvef if self.echocardiography else None
        )
        return float(value) if value is not None else None

    @property
    def egfr(self) -> float | None:
        value = _value(self.labs.egfr)
        return float(value) if value is not None else None

    @property
    def creatinine(self) -> float | None:
        value = _value(self.labs.creatinine)
        return float(value) if value is not None else None

    @property
    def potassium(self) -> float | None:
        value = _value(self.labs.potassium)
        return float(value) if value is not None else None

    @property
    def systolic_bp(self) -> float | None:
        value = _value(self.vitals.systolic_bp)
        return float(value) if value is not None else None

    @property
    def heart_rate(self) -> float | None:
        value = _value(self.vitals.heart_rate)
        return float(value) if value is not None else None

    @property
    def weight_kg(self) -> float | None:
        value = _value(self.vitals.weight_kg)
        return float(value) if value is not None else None

    @property
    def inr(self) -> float | None:
        value = _value(self.labs.inr)
        return float(value) if value is not None else None

    @property
    def inr_target_low(self) -> float | None:
        return self.care_context.inr_target_low

    @property
    def inr_target_high(self) -> float | None:
        return self.care_context.inr_target_high

    @property
    def nyha_class(self) -> str | None:
        return self.heart_failure_profile.nyha_class

    @property
    def comorbidities(self) -> list[str]:
        return [item.normalized_name or item.name for item in self.conditions if item.status != "ruled_out"]

    @property
    def current_medications(self) -> list[str]:
        return [item.normalized_name or item.name for item in self.medications if item.status == "active"]

    @property
    def allergies(self) -> list[str]:
        return [
            item.normalized_substance or item.substance
            for item in self.allergy_statements
            if item.status == "active"
        ]

    def legacy_summary(self) -> dict[str, Any]:
        return {
            "case_id": self.case_id,
            "age": self.age,
            "sex": self.sex,
            "lvef": self.lvef,
            "egfr": self.egfr,
            "creatinine": self.creatinine,
            "potassium": self.potassium,
            "systolic_bp": self.systolic_bp,
            "heart_rate": self.heart_rate,
            "nyha_class": self.nyha_class,
            "comorbidities": self.comorbidities,
            "current_medications": self.current_medications,
            "allergies": self.allergies,
        }
