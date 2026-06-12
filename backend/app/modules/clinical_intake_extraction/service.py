import re
import unicodedata

from app.schemas.patient import (
    AllergyStatement,
    CareContext,
    ClinicalValue,
    Condition,
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


def extract_patient_from_message(message: str, conversation_id: str) -> PatientProfile:
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
