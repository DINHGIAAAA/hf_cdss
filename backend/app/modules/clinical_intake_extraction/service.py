import json
import re
import unicodedata
from typing import Any

from app.core.config import settings
from app.core.http_client import get_async_client, request_with_retry, _build_retry_config
from app.core.llm_runtime import chat_completions_url, llm_auth_headers, llm_chat_completions_enabled
from app.modules.drug_normalization.service import medications_catalog_for_intake
from app.prompts.clinical_intake import CLINICAL_INTAKE_SYSTEM_PROMPT
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


MEDICATIONS: dict[str, tuple[str, tuple[str, ...]]] = medications_catalog_for_intake()

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

# Prompt injection patterns to detect and remove
_PROMPT_INJECTION_PATTERNS = [
    r"ignore\s+(previous|all|above)\s+(instructions?|prompts?|context)",
    r"(disregard|forget)\s+(previous|all|above)\s+(instructions?|prompts?|context)",
    r"(you\s+are\s+now|pretend\s+to\s+be|act\s+as)\s+(a\s+)?different",
    r"(system|assistant)\s*:\s*",
    r"#\s*(instructions?|system|prompt)",
    r"<\s*system\s*>",
    r"new\s+system\s+prompt",
    r"override\s+(safety|restrictions?|guidelines?)",
    r"ignore\s+safety",
    r"(ignore|disregard)\s+the\s+(rules?|constraints?)",
]

_COMPILED_INJECTION_PATTERNS = [re.compile(p, re.IGNORECASE) for p in _PROMPT_INJECTION_PATTERNS]


def _sanitize_llm_input(text: str) -> str:
    """
    Sanitize user input before sending to LLM to prevent prompt injection attacks.
    Removes potential prompt injection patterns while preserving clinical content.
    """
    if not text:
        return text

    # Truncate to max length first
    sanitized = text[:12000]

    # Remove prompt injection patterns
    for pattern in _COMPILED_INJECTION_PATTERNS:
        sanitized = pattern.sub("[CONTENT REDACTED]", sanitized)

    # Normalize Unicode characters (防止 homoglyph attacks)
    sanitized = unicodedata.normalize("NFKC", sanitized)

    # Remove excessive whitespace that might be used for obfuscation
    sanitized = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", sanitized)

    return sanitized.strip()

NO_RED_FLAG_TERMS = (
    "no acute instability",
    "no red flags",
    "stable",
    "khong co dau hieu cap cuu",
    "khong soc",
    "khong chay mau",
)

NEGATION_PREFIXES = ("no", "not", "not on", "without", "denies", "khong", "khong co", "chua ghi nhan")


def normalize_text(text: str) -> str:
    decomposed = unicodedata.normalize("NFD", text)
    ascii_text = "".join(char for char in decomposed if unicodedata.category(char) != "Mn")
    return ascii_text.lower().replace("đ", "d")


def extract_current_message(aggregated_message: str) -> str:
    for line in aggregated_message.splitlines():
        if line.startswith("[Current]"):
            return line.removeprefix("[Current]").strip()
    return aggregated_message.strip()


def _numeric_search_texts(message: str) -> tuple[str, str, str, str]:
    current = extract_current_message(message)
    if current and "[Current]" in message:
        return current, normalize_text(current), message, normalize_text(message)
    normalized = normalize_text(message)
    return message, normalized, message, normalized


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
    primary_text, normalized_primary, full_text, normalized_full = _numeric_search_texts(message)
    normalized = normalized_full

    def measured(patterns: tuple[str, ...]) -> tuple[float | None, str]:
        value, matched = _num(patterns, primary_text, normalized_primary)
        if value is None and primary_text != full_text:
            value, matched = _num(patterns, full_text, normalized_full)
        return value, matched

    lvef, lvef_text = measured(
        (
            r"\b(?:lvef|ef)\s*(?:is|was|=|:|con|khoang|about|around)?\s*(\d+(?:[.,]\d+)?)\s*%?",
            r"\b(?:ejection fraction|phan suat tong mau)\s*(?:is|was|=|:|con|khoang)?\s*(\d+(?:[.,]\d+)?)",
        ),
    )
    egfr, egfr_text = measured(
        (
            r"\b(?:egfr|e-gfr)\s*(?:is|was|=|:|khoang|about)?\s*(\d+(?:[.,]\d+)?)",
            r"\b(?:muc loc cau than|loc cau than)\s*(?:la|khoang|about)?\s*(\d+(?:[.,]\d+)?)",
        ),
    )
    potassium, potassium_text = measured(
        (
            r"\b(?:potassium|serum k|kali|k\+?|k)\s*(?:mau|is|was|=|:|la|khoang)?\s*(\d+(?:[.,]\d+)?)",
        ),
    )
    systolic_bp, sbp_text = measured(
        (
            r"\b(?:sbp|systolic(?: bp)?|huyet ap tam thu)\s*(?:is|was|=|:|la|khoang)?\s*(\d+(?:[.,]\d+)?)",
            r"\b(?:bp|blood pressure|huyet ap|ha)\s*(?:is|was|=|:|la|khoang)?\s*(\d{2,3})(?:/\d{2,3})?",
        ),
    )
    heart_rate, hr_text = measured(
        (
            r"\b(?:hr|heart rate|pulse|nhip tim|mach)\s*(?:is|was|=|:|la|khoang)?\s*(\d+(?:[.,]\d+)?)",
            r"\b(\d+(?:[.,]\d+)?)\s*(?:bpm|lan/phut)\b",
        ),
    )
    weight_kg, weight_text = measured(
        (
            r"\b(?:weight|body weight|can nang|cn)\s*(?:is|was|=|:|la|khoang)?\s*(\d+(?:[.,]\d+)?)\s*kg?\b",
            r"\b(\d+(?:[.,]\d+)?)\s*kg\b",
        ),
    )
    inr, inr_text = measured(
        (
            r"\b(?:inr|prothrombin time|pt)\s*(?:is|was|=|:|la|khoang)?\s*(\d+(?:[.,]\d+)?)",
            r"\b(?:muc inr|chi so inr)\s*(?:la|khoang)?\s*(\d+(?:[.,]\d+)?)",
        ),
    )

    inr_target_low = None
    inr_target_high = None
    inr_target_match = re.search(
        r"\b(?:inr\s*)?target(?:\s*inr)?\s*(?:is|was|=|:|la|khoang)?\s*(\d+(?:[.,]\d+)?)\s*(?:-|to|den|đến)\s*(\d+(?:[.,]\d+)?)",
        normalized,
    )
    if inr_target_match:
        inr_target_low = float(inr_target_match.group(1).replace(",", "."))
        inr_target_high = float(inr_target_match.group(2).replace(",", "."))

    acei_last_dose_hours_ago = None
    acei_hours_match = re.search(
        r"\b(?:last\s+)?(?:acei|ace inhibitor|enalapril|lisinopril|ramipril|captopril)\s+"
        r"(?:dose\s+)?(?:was\s+)?(\d+(?:[.,]\d+)?)\s*(?:hours?|h|gio|giờ)\s+ago",
        normalized,
    )
    if acei_hours_match:
        acei_last_dose_hours_ago = float(acei_hours_match.group(1).replace(",", "."))

    age_match = re.search(
        r"\b(?:age|tuoi)\s*(?:is|was|=|:|la|khoang)?\s*(\d{1,3})\b",
        normalized,
    )
    age = int(age_match.group(1)) if age_match else None
    sex = None
    if re.search(r"\b(?:male|nam|man)\b", normalized):
        sex = "male"
    elif re.search(r"\b(?:female|nu|woman)\b", normalized):
        sex = "female"

    return PatientProfile(
        patient_identity=PatientIdentity(case_id=conversation_id),
        demographics=Demographics(age=age, sex=sex),
        heart_failure_profile=HeartFailureProfile(lvef=_clinical_value(lvef, "%", "lvef", lvef_text)),
        labs=Labs(
            egfr=_clinical_value(egfr, "mL/min/1.73m2", "egfr", egfr_text),
            potassium=_clinical_value(potassium, "mmol/L", "potassium", potassium_text),
            inr=_clinical_value(inr, "", "inr", inr_text),
        ),
        vitals=Vitals(
            systolic_bp=_clinical_value(systolic_bp, "mmHg", "systolic_bp", sbp_text),
            heart_rate=_clinical_value(heart_rate, "bpm", "heart_rate", hr_text),
            weight_kg=_clinical_value(weight_kg, "kg", "weight_kg", weight_text),
        ),
        conditions=_extract_conditions(normalized),
        medications=_extract_medications(message, normalized),
        allergy_statements=_extract_allergies(message, normalized),
        red_flags=_extract_red_flags(normalized),
        care_context=CareContext(
            clinician_question=message,
            acei_last_dose_hours_ago=acei_last_dose_hours_ago,
            inr_target_low=inr_target_low,
            inr_target_high=inr_target_high,
        ),
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


def _llm_extractor_available() -> bool:
    return llm_chat_completions_enabled()


async def _call_llm_extractor(message: str) -> dict[str, Any] | None:
    if not _llm_extractor_available():
        return None
    try:
        client = get_async_client(
            "clinical_intake",
            settings.clinical_intake_llm_timeout_seconds,
            max_connections=4,
        )
        # Use retry logic for LLM calls
        retry_config = _build_retry_config(
            max_retries=2,  # 3 attempts total
            base_delay=1.0,
            max_delay=10.0,
            retry_on_status={500, 502, 503, 504, 429},  # Retry on server errors and rate limits
        )
        response = await request_with_retry(
            client,
            "POST",
            chat_completions_url(),
            headers=llm_auth_headers(),
            json={
                "model": settings.llm_model,
                "messages": [
                    {"role": "system", "content": CLINICAL_INTAKE_SYSTEM_PROMPT},
                    {"role": "user", "content": _sanitize_llm_input(message)},
                ],
                "temperature": 0,
                "max_tokens": settings.clinical_intake_llm_max_tokens,
            },
            retry_config=retry_config,
        )
        response.raise_for_status()
        choices = response.json().get("choices", [])
        content = choices[0].get("message", {}).get("content", "") if choices else ""
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
            inr=_clinical_value_llm(data.get("inr"), "", "inr"),
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
        care_context=CareContext(
            clinician_question=message,
            acei_last_dose_hours_ago=_as_float(data.get("acei_last_dose_hours_ago")),
            inr_target_low=_as_float(data.get("inr_target_low")),
            inr_target_high=_as_float(data.get("inr_target_high")),
        ),
    )


def _prefer(existing: Any, incoming: Any) -> Any:
    return incoming if incoming not in (None, [], "") else existing


def _has_clinical_value(value: ClinicalValue | None) -> bool:
    return value is not None and value.value is not None


def _prefer_measured(regex_value: ClinicalValue | None, llm_value: ClinicalValue | None) -> ClinicalValue | None:
    if _has_clinical_value(regex_value):
        return regex_value
    if _has_clinical_value(llm_value):
        return llm_value
    return regex_value


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
    patient.vitals.weight_kg = _prefer_measured(patient.vitals.weight_kg, llm_patient.vitals.weight_kg)
    patient.vitals.systolic_bp = _prefer_measured(patient.vitals.systolic_bp, llm_patient.vitals.systolic_bp)
    patient.vitals.diastolic_bp = _prefer_measured(patient.vitals.diastolic_bp, llm_patient.vitals.diastolic_bp)
    patient.vitals.heart_rate = _prefer_measured(patient.vitals.heart_rate, llm_patient.vitals.heart_rate)
    patient.heart_failure_profile.lvef = _prefer_measured(
        patient.heart_failure_profile.lvef,
        llm_patient.heart_failure_profile.lvef,
    )
    patient.heart_failure_profile.hf_type = _prefer(
        patient.heart_failure_profile.hf_type,
        llm_patient.heart_failure_profile.hf_type,
    )
    patient.heart_failure_profile.nyha_class = _prefer(
        patient.heart_failure_profile.nyha_class,
        llm_patient.heart_failure_profile.nyha_class,
    )
    patient.labs.egfr = _prefer_measured(patient.labs.egfr, llm_patient.labs.egfr)
    patient.labs.creatinine = _prefer_measured(patient.labs.creatinine, llm_patient.labs.creatinine)
    patient.labs.potassium = _prefer_measured(patient.labs.potassium, llm_patient.labs.potassium)
    patient.labs.inr = _prefer_measured(patient.labs.inr, llm_patient.labs.inr)
    patient.care_context.acei_last_dose_hours_ago = _prefer(
        patient.care_context.acei_last_dose_hours_ago,
        llm_patient.care_context.acei_last_dose_hours_ago,
    )
    patient.care_context.inr_target_low = _prefer(
        patient.care_context.inr_target_low,
        llm_patient.care_context.inr_target_low,
    )
    patient.care_context.inr_target_high = _prefer(
        patient.care_context.inr_target_high,
        llm_patient.care_context.inr_target_high,
    )
    patient.chief_complaint = _prefer(patient.chief_complaint, llm_patient.chief_complaint)
    patient.conditions = _merge_named(patient.conditions, llm_patient.conditions, "name")
    patient.medications = _merge_named(patient.medications, llm_patient.medications, "name")
    patient.allergy_statements = _merge_named(patient.allergy_statements, llm_patient.allergy_statements, "substance")
    patient.red_flags = _merge_named(patient.red_flags, llm_patient.red_flags, "name")
    return patient


async def extract_patient_from_message(
    message: str,
    conversation_id: str,
    *,
    conversation_history: list[str] | None = None,
) -> PatientProfile:
    from app.modules.clinical_intake_extraction.semantic import aggregate_conversation_context, semantic_extract_patient
    from app.modules.clinical_intake_extraction.selective_llm import should_call_llm_extractor

    aggregated_message = aggregate_conversation_context(message, conversation_history or [])
    regex_patient = _regex_extract_patient_from_message(aggregated_message, conversation_id)
    semantic_patient = semantic_extract_patient(aggregated_message, conversation_id)
    merged = _merge_extractions(regex_patient, semantic_patient)
    decision = should_call_llm_extractor(
        aggregated_message=aggregated_message,
        regex_patient=regex_patient,
        semantic_patient=semantic_patient,
        merged=merged,
    )
    if not decision.call_llm:
        return merged
    llm_data = await _call_llm_extractor(aggregated_message)
    llm_patient = _patient_from_llm_data(llm_data, conversation_id, aggregated_message) if llm_data else None
    return _merge_extractions(merged, llm_patient)


def extract_patient_from_message_sync(
    message: str,
    conversation_id: str,
    *,
    conversation_history: list[str] | None = None,
) -> PatientProfile:
    """Blocking helper for tests and scripts without a running event loop."""
    import asyncio

    return asyncio.run(
        extract_patient_from_message(
            message,
            conversation_id,
            conversation_history=conversation_history,
        )
    )
