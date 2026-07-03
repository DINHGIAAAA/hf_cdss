"""Convert CDSS audit events into clinical intake SFT records."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from training.intake_finetune.sft_format import to_sft_record


def _patient_label(patient: dict[str, Any]) -> dict[str, Any]:
    return {
        "case_id": patient.get("case_id"),
        "age": patient.get("age"),
        "sex": patient.get("sex"),
        "lvef": patient.get("lvef"),
        "egfr": patient.get("egfr"),
        "potassium": patient.get("potassium"),
        "systolic_bp": patient.get("systolic_bp"),
        "heart_rate": patient.get("heart_rate"),
        "weight_kg": patient.get("weight_kg"),
        "creatinine": patient.get("creatinine"),
        "inr": patient.get("inr"),
        "comorbidities": list(patient.get("comorbidities") or []),
        "current_medications": list(patient.get("current_medications") or []),
        "allergies": list(patient.get("allergies") or []),
    }


def convert_audit_event(event: dict[str, Any]) -> dict[str, Any] | None:
    payload = event.get("payload") or {}
    message = str(payload.get("message") or "").strip()
    patient = payload.get("patient") or {}
    if not message or not isinstance(patient, dict):
        return None
    label = _patient_label(patient)
    if not any(label.get(key) is not None for key in ("lvef", "egfr", "potassium", "systolic_bp", "heart_rate")):
        if not label.get("current_medications") and not label.get("comorbidities"):
            return None
    source = f"audit:{event.get('event_type') or 'unknown'}"
    return to_sft_record(message, label, source=source)


def convert_audit_jsonl(path: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    if not path.exists():
        return records
    with path.open(encoding="utf-8-sig") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            event = json.loads(line)
            record = convert_audit_event(event)
            if record:
                records.append(record)
    return records
