"""Detect medication-class focus and binary choice questions from clinician text."""

from __future__ import annotations

import re
from typing import Any

from app.modules.clinical_intake_extraction.service import normalize_text
from app.modules.recommendation.drug_class_keys import canonical_gdmt_class_id
from app.schemas.llm import LLMAnswerRequest

_KEYWORD_TO_CLASS_ID: dict[str, str] = {
    "mra": "mra",
    "mineralocorticoid": "mra",
    "aldosterone": "mra",
    "spironolactone": "mra",
    "eplerenone": "mra",
    "finerenone": "mra",
    "sglt2": "sglt2i",
    "sglt2i": "sglt2i",
    "dapagliflozin": "sglt2i",
    "empagliflozin": "sglt2i",
    "canagliflozin": "sglt2i",
    "arni": "arni",
    "entresto": "arni",
    "sacubitril": "arni",
    "ramipril": "acei_arb",
    "lisinopril": "acei_arb",
    "enalapril": "acei_arb",
    "perindopril": "acei_arb",
    "losartan": "acei_arb",
    "valsartan": "acei_arb",
    "candesartan": "acei_arb",
    "ace inhibitor": "acei_arb",
    "arb": "acei_arb",
    "beta blocker": "beta_blocker",
    "bisoprolol": "beta_blocker",
    "metoprolol": "beta_blocker",
    "carvedilol": "beta_blocker",
    "nebivolol": "beta_blocker",
    "loop diuretic": "loop_diuretic",
    "furosemide": "loop_diuretic",
    "bumetanide": "loop_diuretic",
    "torsemide": "loop_diuretic",
}

_CHOICE_CONNECTOR_RE = re.compile(
    r"\b(hoac|hay|hoặc|or|va\/|và\/|lua chon|lựa chọn)\b",
    re.IGNORECASE,
)


def focus_class_ids_from_message(message: str) -> set[str]:
    normalized = normalize_text(message or "")
    focus: set[str] = set()
    for keyword, class_id in _KEYWORD_TO_CLASS_ID.items():
        pattern = rf"(?<![a-z0-9]){re.escape(keyword)}(?![a-z0-9])"
        if re.search(pattern, normalized):
            focus.add(class_id)
    return focus


def focus_class_ids_from_state(clinical_state: dict[str, Any] | None) -> set[str]:
    if not clinical_state:
        return set()
    focus: set[str] = set()
    for raw in clinical_state.get("focus_medication_classes") or []:
        if not raw:
            continue
        cid = canonical_gdmt_class_id(str(raw)) or str(raw).lower().strip()
        if cid:
            focus.add(cid)
    return focus


def merged_focus_class_ids(*, message: str, clinical_state: dict[str, Any] | None) -> set[str]:
    focus = focus_class_ids_from_state(clinical_state)
    focus.update(focus_class_ids_from_message(message))
    return focus


def is_choice_question(message: str) -> bool:
    normalized = normalize_text(message or "")
    if not normalized:
        return False
    if not _CHOICE_CONNECTOR_RE.search(normalized):
        return False
    return len(focus_class_ids_from_message(message)) >= 2


def is_mra_vs_sglt2_choice(message: str, clinical_state: dict[str, Any] | None = None) -> bool:
    if not is_choice_question(message):
        return False
    focus = merged_focus_class_ids(message=message, clinical_state=clinical_state)
    return "mra" in focus and "sglt2i" in focus


def focus_class_ids_for_payload(payload: LLMAnswerRequest) -> set[str]:
    return merged_focus_class_ids(message=payload.user_input or "", clinical_state=payload.clinical_state)
