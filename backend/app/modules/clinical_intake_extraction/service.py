import json
import re
import unicodedata
from typing import Any

import httpx

from app.core.config import settings
from app.schemas.patient import (
    AllergyStatement,
    CareContext,
    ChiefComplaint,
    ClinicalValue,
    Condition,
    Demographics,
    HeartFailureProfile,
    Labs,
    MedicationStatement,
    PatientIdentity,
    PatientProfile,
    RedFlag,
    SourceTrace,
    Vitals,
)


MEDICATIONS: dict[str, tuple[str, tuple[str, ...]]] = {
    "spironolactone": ("MRA", ("spironolactone", "aldactone")),
    "eplerenone": ("MRA", ("eplerenone",)),
    "finerenone": ("MRA", ("finerenone",)),
    "metoprolol": ("beta_blocker", ("metoprolol", "metoprolol succinate", "toprol")),
    "bisoprolol": ("beta_blocker", ("bisoprolol",)),
    "carvedilol": ("beta_blocker", ("carvedilol",)),
    "lisinopril": ("ACEi", ("lisinopril",)),
    "enalapril": ("ACEi", ("enalapril",)),
    "losartan": ("ARB", ("losartan",)),
    "valsartan": ("ARB", ("valsartan",)),
    "candesartan": ("ARB", ("candesartan",)),
    "sacubitril/valsartan": ("ARNI", ("sacubitril/valsartan", "sacubitril valsartan", "entresto")),
    "dapagliflozin": ("SGLT2i", ("dapagliflozin", "farxiga")),
    "empagliflozin": ("SGLT2i", ("empagliflozin", "jardiance")),
    "furosemide": ("loop_diuretic", ("furosemide", "lasix")),
    "torsemide": ("loop_diuretic", ("torsemide",)),
    "bumetanide": ("loop_diuretic", ("bumetanide",)),
    "ivabradine": ("heart_rate_agent", ("ivabradine", "corlanor")),
    "digoxin": ("cardiac_glycoside", ("digoxin",)),
    "apixaban": ("anticoagulant", ("apixaban", "eliquis")),
    "warfarin": ("anticoagulant", ("warfarin",)),
    "aspirin": ("antiplatelet", ("aspirin",)),
    "clopidogrel": ("antiplatelet", ("clopidogrel",)),
    "amlodipine": ("calcium_channel_blocker", ("amlodipine",)),
    "atorvastatin": ("statin", ("atorvastatin",)),
    "hydralazine": ("vasodilator", ("hydralazine",)),
    "isosorbide dinitrate": ("nitrate", ("isosorbide dinitrate",)),
    "patiromer": ("potassium_binder", ("patiromer",)),
    "sodium zirconium cyclosilicate": (
        "potassium_binder",
        ("sodium zirconium cyclosilicate", "lokelma"),
    ),
}

CONDITIONS: dict[str, tuple[str, ...]] = {
    "CKD": ("ckd", "chronic kidney", "suy than", "benh than man", "than man"),
    "Diabetes": ("diabetes", "dm", "t2dm", "tieu duong", "dai thao duong"),
    "Atrial fibrillation": ("atrial fibrillation", "afib", "af ", "rung nhi"),
    "Hypertension": ("hypertension", "htn", "tang huyet ap"),
    "COPD": ("copd", "asthma", "hen", "benh phoi tac nghen"),
}

RED_FLAGS: dict[str, tuple[str, ...]] = {
    "cardiogenic_shock": ("cardiogenic shock", "shock", "soc tim"),
    "active_bleeding": ("active bleeding", "dang chay mau", "xuat huyet dang tien trien"),
    "acute_decompensated_hf": (
        "acute decompensated",
        "decompensated hf",
        "kho tho tang",
        "phu chan",
        "suy tim mat bu",
    ),
}

NO_RED_FLAG_TERMS = (
    "no acute instability",
    "no red flags",
    "stable",
    "khong co dau hieu cap cuu",
    "khong soc",
    "khong chay mau",
)

NEGATION_PREFIXES = ("no", "not", "not on", "without", "denies", "khong", "khong co", "chua ghi nhan")

LLM_SYSTEM_PROMPT = """You extract structured heart-failure patient intake from clinical text.
Return JSON only. Do not invent missing values. Use null for unknown scalar values and [] for unknown lists.
Prefer explicit values from the text over inference.
Schema:
{
  "full_name": string|null,
  "age": number|null,
  "sex": "male"|"female"|null,
  "weight_kg": number|null,
  "systolic_bp": number|null,
  "diastolic_bp": number|null,
  "heart_rate": number|null,
  "lvef": number|null,
  "hf_type": string|null,
  "nyha_class": string|null,
  "egfr": number|null,
  "creatinine": number|null,
  "potassium": number|null,
  "conditions": [string],
  "medications": [{"name": string, "dose_value": number|null, "dose_unit": string|null, "frequency": string|null}],
  "allergies": [string],
  "red_flags": [{"name": string, "status": "present"|"absent"}],
  "chief_complaint": string|null
}
"""


def normalize_text(text: str) -> str:
    decomposed = unicodedata.normalize("NFD", text)
    ascii_text = "".join(char for char in decomposed if unicodedata.category(char) != "Mn")
    return ascii_text.lower().replace("đ", "d")


def _source(field: str, raw: str, confidence: float = 0.9) -> SourceTrace:
    return SourceTrace(source_type="chat", document_id=field, source_text=raw[:240], confidence=confidence)


def _clinical_value(value: float | None, unit: str, field: str, raw: str) -> ClinicalValue | None:
    if value is None:
        return None
    return ClinicalValue(value=value, unit=unit, source=_source(field, raw))


def _as_float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(str(value).replace(",", "."))
    except (TypeError, ValueError):
        return None


def _as_int(value: Any) -> int | None:
    parsed = _as_float(value)
    return int(parsed) if parsed is not None else None


def _source_llm(field: str, raw: Any) -> SourceTrace:
    return SourceTrace(source_type="llm_clinical_intake", document_id=field, source_text=str(raw)[:240], confidence=0.78)


def _clinical_value_llm(value: Any, unit: str, field: str) -> ClinicalValue | None:
    parsed = _as_float(value)
    if parsed is None:
        return None
    return ClinicalValue(value=parsed, unit=unit, source=_source_llm(field, value))


def _num(patterns: tuple[str, ...], raw_text: str, normalized_text: str) -> tuple[float | None, str]:
    for pattern in patterns:
        match = re.search(pattern, normalized_text, flags=re.IGNORECASE)
        if match:
            try:
                return float(match.group(1).replace(",", ".")), match.group(0)
            except ValueError:
                return None, ""
    return None, ""


def _is_negated(normalized_text: str, start: int) -> bool:
    context = normalized_text[max(0, start - 24) : start]
    return any(re.search(rf"\b{re.escape(prefix)}\b(?:\s+\w+)?\s*$", context) for prefix in NEGATION_PREFIXES)


def _find_terms(normalized_text: str, terms: tuple[str, ...]) -> list[re.Match]:
    matches: list[re.Match] = []
    for term in sorted(terms, key=len, reverse=True):
        pattern = rf"(?<![a-z0-9]){re.escape(term)}(?![a-z0-9])"
        matches.extend(re.finditer(pattern, normalized_text))
    return sorted(matches, key=lambda item: item.start())


def _extract_conditions(normalized_text: str) -> list[Condition]:
    conditions: list[Condition] = []
    for name, terms in CONDITIONS.items():
        matches = _find_terms(normalized_text, terms)
        if any(not _is_negated(normalized_text, match.start()) for match in matches):
            conditions.append(Condition(name=name, status="active", source=_source("condition", name)))
    return conditions


def _extract_red_flags(normalized_text: str) -> list[RedFlag]:
    red_flags: list[RedFlag] = []
    for name, terms in RED_FLAGS.items():
        matches = _find_terms(normalized_text, terms)
        if any(not _is_negated(normalized_text, match.start()) for match in matches):
            red_flags.append(RedFlag(name=name, status="present", source=_source("red_flag", name)))
    if not red_flags and any(term in normalized_text for term in NO_RED_FLAG_TERMS):
        red_flags.append(
            RedFlag(name="no_acute_instability_reported", status="absent", source=_source("red_flag", "stable"))
        )
    return red_flags


def _extract_medications(raw_text: str, normalized_text: str) -> list[MedicationStatement]:
    medications: list[MedicationStatement] = []
    seen: set[str] = set()
    for canonical_name, (drug_class, aliases) in MEDICATIONS.items():
        matches = _find_terms(normalized_text, aliases)
        active_matches = [match for match in matches if not _is_negated(normalized_text, match.start())]
        if not active_matches or canonical_name in seen:
            continue
        match = active_matches[0]
        window = normalized_text[match.start() : min(len(normalized_text), match.end() + 48)]
        dose = re.search(r"(\d+(?:[.,]\d+)?)\s*(mg|mcg|g|units?)", window)
        frequency = re.search(r"\b(qd|daily|od|bid|tid|qhs|once daily|twice daily|hang ngay|moi ngay)\b", window)
        medications.append(
            MedicationStatement(
                name=canonical_name,
                drug_class=drug_class,
                dose_value=float(dose.group(1).replace(",", ".")) if dose else None,
                dose_unit=dose.group(2) if dose else None,
                frequency=frequency.group(1) if frequency else None,
                status="active",
                source=_source("medication", raw_text[max(0, match.start() - 20) : match.end() + 60]),
            )
        )
        seen.add(canonical_name)
    return medications


def _extract_allergies(raw_text: str, normalized_text: str) -> list[AllergyStatement]:
    no_allergy_terms = (
        "no known drug allergies",
        "no allergies",
        "nkda",
        "khong di ung",
        "chua ghi nhan di ung",
    )
    if any(term in normalized_text for term in no_allergy_terms):
        return [
            AllergyStatement(
                substance="no known drug allergies",
                status="active",
                source=_source("allergy", "no known drug allergies"),
            )
        ]

    patterns = (
        r"(?:allergy|allergic to|di ung|di ung voi)\s*:?\s*([a-z0-9+/\- ]{2,80})",
        r"(?:angioedema|phu mach|cough|ho)\s+(?:with|voi|do)\s+([a-z0-9+/\- ]{2,40})",
    )
    allergies: list[AllergyStatement] = []
    for pattern in patterns:
        match = re.search(pattern, normalized_text)
        if match:
            substance = re.split(r"[,.;]", match.group(1).strip())[0].strip()
            substance = re.sub(r"^(?:voi|with|to)\s+", "", substance).strip()
            if substance:
                allergies.append(
                    AllergyStatement(
                        substance=substance,
                        reaction=match.group(0).strip(),
                        status="active",
                        source=_source("allergy", match.group(0)),
                    )
                )
    return allergies


def _regex_extract_patient_from_message(message: str, conversation_id: str) -> PatientProfile:
    normalized = normalize_text(message)
    lvef, lvef_text = _num(
        (
            r"\b(?:lvef|ef)\s*(?:is|was|=|:|con|khoang|about|around)?\s*(\d+(?:[.,]\d+)?)\s*%?",
            r"\b(?:ejection fraction|phan suat tong mau)\s*(?:is|was|=|:|con|khoang)?\s*(\d+(?:[.,]\d+)?)",
        ),
        message,
        normalized,
    )
    egfr, egfr_text = _num(
        (
            r"\b(?:egfr|e-gfr)\s*(?:is|was|=|:|khoang|about)?\s*(\d+(?:[.,]\d+)?)",
            r"\b(?:muc loc cau than|loc cau than)\s*(?:la|khoang|about)?\s*(\d+(?:[.,]\d+)?)",
        ),
        message,
        normalized,
    )
    potassium, potassium_text = _num(
        (
            r"\b(?:potassium|serum k|kali|k\+?|k)\s*(?:mau|is|was|=|:|la|khoang)?\s*(\d+(?:[.,]\d+)?)",
        ),
        message,
        normalized,
    )
    systolic_bp, sbp_text = _num(
        (
            r"\b(?:sbp|systolic(?: bp)?|huyet ap tam thu)\s*(?:is|was|=|:|la|khoang)?\s*(\d+(?:[.,]\d+)?)",
            r"\b(?:bp|blood pressure|huyet ap|ha)\s*(?:is|was|=|:|la|khoang)?\s*(\d{2,3})(?:/\d{2,3})?",
        ),
        message,
        normalized,
    )
    heart_rate, hr_text = _num(
        (
            r"\b(?:hr|heart rate|pulse|nhip tim|mach)\s*(?:is|was|=|:|la|khoang)?\s*(\d+(?:[.,]\d+)?)",
            r"\b(\d+(?:[.,]\d+)?)\s*(?:bpm|lan/phut)\b",
        ),
        message,
        normalized,
    )

    return PatientProfile(
        patient_identity=PatientIdentity(case_id=conversation_id),
        heart_failure_profile=HeartFailureProfile(lvef=_clinical_value(lvef, "%", "lvef", lvef_text)),
        labs=Labs(
            egfr=_clinical_value(egfr, "mL/min/1.73m2", "egfr", egfr_text),
            potassium=_clinical_value(potassium, "mmol/L", "potassium", potassium_text),
        ),
        vitals=Vitals(
            systolic_bp=_clinical_value(systolic_bp, "mmHg", "systolic_bp", sbp_text),
            heart_rate=_clinical_value(heart_rate, "bpm", "heart_rate", hr_text),
        ),
        conditions=_extract_conditions(normalized),
        medications=_extract_medications(message, normalized),
        allergy_statements=_extract_allergies(message, normalized),
        red_flags=_extract_red_flags(normalized),
        care_context=CareContext(clinician_question=message),
    )


def _extract_json_object(text: str) -> dict[str, Any] | None:
    stripped = text.strip()
    if not stripped:
        return None
    try:
        data = json.loads(stripped)
        return data if isinstance(data, dict) else None
    except json.JSONDecodeError:
        pass
    match = re.search(r"\{.*\}", stripped, flags=re.DOTALL)
    if not match:
        return None
    try:
        data = json.loads(match.group(0))
        return data if isinstance(data, dict) else None
    except json.JSONDecodeError:
        return None


def _llm_enabled() -> bool:
    if not settings.clinical_intake_llm_enabled:
        return False
    api_type = settings.llm_api_type.lower().strip()
    if api_type == "responses" and "api.openai.com" in settings.llm_base_url and not settings.openai_api_key:
        return False
    return True


def _auth_headers() -> dict[str, str]:
    headers = {"Content-Type": "application/json"}
    if settings.openai_api_key:
        headers["Authorization"] = f"Bearer {settings.openai_api_key}"
    return headers


def _call_llm_extractor(message: str) -> dict[str, Any] | None:
    if not _llm_enabled():
        return None
    api_type = settings.llm_api_type.lower().strip()
    try:
        with httpx.Client(timeout=settings.clinical_intake_llm_timeout_seconds) as client:
            if api_type == "chat_completions":
                response = client.post(
                    f"{settings.llm_base_url.rstrip('/')}/chat/completions",
                    headers=_auth_headers(),
                    json={
                        "model": settings.llm_model,
                        "messages": [
                            {"role": "system", "content": LLM_SYSTEM_PROMPT},
                            {"role": "user", "content": message[:12000]},
                        ],
                        "temperature": 0,
                        "max_tokens": settings.clinical_intake_llm_max_tokens,
                    },
                )
                response.raise_for_status()
                choices = response.json().get("choices", [])
                content = choices[0].get("message", {}).get("content", "") if choices else ""
            else:
                response = client.post(
                    f"{settings.llm_base_url.rstrip('/')}/responses",
                    headers=_auth_headers(),
                    json={
                        "model": settings.llm_model,
                        "instructions": LLM_SYSTEM_PROMPT,
                        "input": message[:12000],
                        "max_output_tokens": settings.clinical_intake_llm_max_tokens,
                        "text": {"format": {"type": "json_object"}},
                    },
                )
                response.raise_for_status()
                payload = response.json()
                content = payload.get("output_text", "")
                if not content:
                    parts = []
                    for item in payload.get("output", []):
                        for block in item.get("content", []):
                            if isinstance(block.get("text"), str):
                                parts.append(block["text"])
                    content = "\n".join(parts)
        return _extract_json_object(content)
    except Exception:
        return None


def _medication_from_llm(item: Any) -> MedicationStatement | None:
    if isinstance(item, str):
        name = item.strip()
        dose_value = None
        dose_unit = None
        frequency = None
    elif isinstance(item, dict):
        name = str(item.get("name") or "").strip()
        dose_value = _as_float(item.get("dose_value"))
        dose_unit = item.get("dose_unit")
        frequency = item.get("frequency")
    else:
        return None
    if not name:
        return None
    normalized = normalize_text(name)
    drug_class = None
    canonical_name = name
    for candidate, (candidate_class, aliases) in MEDICATIONS.items():
        if any(alias in normalized for alias in aliases):
            canonical_name = candidate
            drug_class = candidate_class
            break
    return MedicationStatement(
        name=canonical_name,
        drug_class=drug_class,
        dose_value=dose_value,
        dose_unit=dose_unit,
        frequency=frequency,
        status="active",
        source=_source_llm("medication", item),
    )


def _patient_from_llm_data(data: dict[str, Any], conversation_id: str, message: str) -> PatientProfile:
    medications = [item for item in (_medication_from_llm(raw) for raw in data.get("medications") or []) if item]
    conditions = [
        Condition(name=str(name), status="active", source=_source_llm("condition", name))
        for name in data.get("conditions") or []
        if str(name).strip()
    ]
    allergies = [
        AllergyStatement(substance=str(name), status="active", source=_source_llm("allergy", name))
        for name in data.get("allergies") or []
        if str(name).strip()
    ]
    red_flags = []
    for raw in data.get("red_flags") or []:
        if isinstance(raw, dict):
            name = str(raw.get("name") or "").strip()
            status = raw.get("status") or "present"
        else:
            name = str(raw).strip()
            status = "present"
        if name:
            red_flags.append(RedFlag(name=name, status=status, source=_source_llm("red_flag", raw)))

    return PatientProfile(
        patient_identity=PatientIdentity(
            case_id=conversation_id,
            full_name=data.get("full_name"),
            preferred_name=data.get("full_name"),
        ),
        demographics=Demographics(age=_as_int(data.get("age")), sex=data.get("sex")),
        chief_complaint=ChiefComplaint(text=data.get("chief_complaint"), source=_source_llm("chief_complaint", data.get("chief_complaint"))) if data.get("chief_complaint") else None,
        heart_failure_profile=HeartFailureProfile(
            lvef=_clinical_value_llm(data.get("lvef"), "%", "lvef"),
            hf_type=data.get("hf_type"),
            nyha_class=data.get("nyha_class"),
        ),
        labs=Labs(
            egfr=_clinical_value_llm(data.get("egfr"), "mL/min/1.73m2", "egfr"),
            creatinine=_clinical_value_llm(data.get("creatinine"), "mg/dL", "creatinine"),
            potassium=_clinical_value_llm(data.get("potassium"), "mmol/L", "potassium"),
        ),
        vitals=Vitals(
            systolic_bp=_clinical_value_llm(data.get("systolic_bp"), "mmHg", "systolic_bp"),
            diastolic_bp=_clinical_value_llm(data.get("diastolic_bp"), "mmHg", "diastolic_bp"),
            heart_rate=_clinical_value_llm(data.get("heart_rate"), "bpm", "heart_rate"),
            weight_kg=_clinical_value_llm(data.get("weight_kg"), "kg", "weight_kg"),
        ),
        conditions=conditions,
        medications=medications,
        allergy_statements=allergies,
        red_flags=red_flags,
        care_context=CareContext(clinician_question=message),
    )


def _prefer(existing: Any, incoming: Any) -> Any:
    return incoming if incoming not in (None, [], "") else existing


def _merge_named(existing: list[Any], incoming: list[Any], attr: str) -> list[Any]:
    by_name = {str(getattr(item, attr)).lower(): item for item in existing}
    for item in incoming:
        key = str(getattr(item, attr)).lower()
        by_name[key] = item
    return list(by_name.values())


def _merge_extractions(regex_patient: PatientProfile, llm_patient: PatientProfile | None) -> PatientProfile:
    if llm_patient is None:
        return regex_patient
    patient = regex_patient.model_copy(deep=True)
    patient.patient_identity.full_name = _prefer(patient.patient_identity.full_name, llm_patient.patient_identity.full_name)
    patient.patient_identity.preferred_name = _prefer(
        patient.patient_identity.preferred_name,
        llm_patient.patient_identity.preferred_name,
    )
    patient.demographics.age = _prefer(patient.demographics.age, llm_patient.demographics.age)
    patient.demographics.sex = _prefer(patient.demographics.sex, llm_patient.demographics.sex)
    patient.vitals.weight_kg = _prefer(patient.vitals.weight_kg, llm_patient.vitals.weight_kg)
    patient.vitals.systolic_bp = _prefer(patient.vitals.systolic_bp, llm_patient.vitals.systolic_bp)
    patient.vitals.diastolic_bp = _prefer(patient.vitals.diastolic_bp, llm_patient.vitals.diastolic_bp)
    patient.vitals.heart_rate = _prefer(patient.vitals.heart_rate, llm_patient.vitals.heart_rate)
    patient.heart_failure_profile.lvef = _prefer(patient.heart_failure_profile.lvef, llm_patient.heart_failure_profile.lvef)
    patient.heart_failure_profile.hf_type = _prefer(patient.heart_failure_profile.hf_type, llm_patient.heart_failure_profile.hf_type)
    patient.heart_failure_profile.nyha_class = _prefer(
        patient.heart_failure_profile.nyha_class,
        llm_patient.heart_failure_profile.nyha_class,
    )
    patient.labs.egfr = _prefer(patient.labs.egfr, llm_patient.labs.egfr)
    patient.labs.creatinine = _prefer(patient.labs.creatinine, llm_patient.labs.creatinine)
    patient.labs.potassium = _prefer(patient.labs.potassium, llm_patient.labs.potassium)
    patient.chief_complaint = _prefer(patient.chief_complaint, llm_patient.chief_complaint)
    patient.conditions = _merge_named(patient.conditions, llm_patient.conditions, "name")
    patient.medications = _merge_named(patient.medications, llm_patient.medications, "name")
    patient.allergy_statements = _merge_named(patient.allergy_statements, llm_patient.allergy_statements, "substance")
    patient.red_flags = _merge_named(patient.red_flags, llm_patient.red_flags, "name")
    return patient


def extract_patient_from_message(message: str, conversation_id: str) -> PatientProfile:
    regex_patient = _regex_extract_patient_from_message(message, conversation_id)
    llm_data = _call_llm_extractor(message)
    llm_patient = _patient_from_llm_data(llm_data, conversation_id, message) if llm_data else None
    return _merge_extractions(regex_patient, llm_patient)
