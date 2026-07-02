from __future__ import annotations

import json
import re
from typing import Any


def empty_intake_label() -> dict[str, Any]:
    return {
        "full_name": None,
        "age": None,
        "sex": None,
        "weight_kg": None,
        "systolic_bp": None,
        "diastolic_bp": None,
        "heart_rate": None,
        "lvef": None,
        "hf_type": None,
        "nyha_class": None,
        "egfr": None,
        "creatinine": None,
        "potassium": None,
        "conditions": [],
        "medications": [],
        "allergies": [],
        "red_flags": [],
        "chief_complaint": None,
    }


def normalize_medication_name(name: str) -> str:
    cleaned = re.sub(r"\s+", " ", name.strip().lower())
    return cleaned


def parse_dose_value(raw: str | None) -> float | None:
    if not raw:
        return None
    match = re.search(r"(\d+(?:\.\d+)?)", raw.replace(",", "."))
    if not match:
        return None
    try:
        return float(match.group(1))
    except ValueError:
        return None


def parse_dose_unit(raw: str | None) -> str | None:
    if not raw:
        return None
    lowered = raw.lower()
    for unit in ("mg", "mcg", "g", "units", "unit", "ml"):
        if unit in lowered:
            return "units" if unit == "unit" else unit
    return None


def dump_intake_label(label: dict[str, Any]) -> str:
    return json.dumps(label, ensure_ascii=False, separators=(",", ":"))
