from __future__ import annotations

import csv
from collections import defaultdict
from pathlib import Path

from training.intake_finetune.schema import empty_intake_label, normalize_medication_name, parse_dose_unit, parse_dose_value
from training.intake_finetune.sft_format import to_sft_record


POTASSIUM_ITEMIDS = {50971, 50822, 227442}
CREATININE_ITEMIDS = {50912}
HEART_RATE_ITEMIDS = {220045}
SYSTOLIC_BP_ITEMIDS = {220050, 220179, 51}
WEIGHT_ITEMIDS = {224639, 226512}


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _latest_numeric(rows: list[dict[str, str]], item_ids: set[int], value_field: str = "valuenum") -> float | None:
    filtered = []
    for row in rows:
        try:
            item_id = int(float(row.get("itemid") or row.get("item_id") or -1))
        except ValueError:
            continue
        if item_id not in item_ids:
            continue
        raw = row.get(value_field) or row.get("value")
        if raw in (None, ""):
            continue
        try:
            value = float(raw)
        except ValueError:
            continue
        filtered.append((row.get("charttime") or row.get("storetime") or "", value))
    if not filtered:
        return None
    filtered.sort(key=lambda item: item[0])
    return filtered[-1][1]


def _hf_hadm_ids(diagnoses_path: Path) -> set[int]:
    if not diagnoses_path.exists():
        return set()
    hadm_ids: set[int] = set()
    for row in _read_csv(diagnoses_path):
        code = (row.get("icd_code") or "").upper()
        version = (row.get("icd_version") or "").strip()
        if version == "10" and code.startswith("I50"):
            hadm_ids.add(int(float(row["hadm_id"])))
        if version == "9" and code.startswith("428"):
            hadm_ids.add(int(float(row["hadm_id"])))
    return hadm_ids


def _medications_for_hadm(prescriptions: list[dict[str, str]], hadm_id: int) -> list[dict]:
    meds: list[dict] = []
    seen: set[str] = set()
    for row in prescriptions:
        if int(float(row["hadm_id"])) != hadm_id:
            continue
        name = normalize_medication_name(row.get("drug") or row.get("drug_name") or "")
        if not name or name in seen:
            continue
        seen.add(name)
        meds.append(
            {
                "name": name,
                "dose_value": parse_dose_value(row.get("dose_val_rx")),
                "dose_unit": parse_dose_unit(row.get("dose_unit_rx")),
                "frequency": row.get("doses_per_24_hrs"),
            }
        )
    return meds


def _render_note(
  *,
  heart_rate: float | None,
  systolic_bp: float | None,
  potassium: float | None,
  creatinine: float | None,
  weight_kg: float | None,
  medications: list[dict],
) -> str:
    parts = ["Heart failure hospitalization summary."]
    if heart_rate is not None:
        parts.append(f"Heart rate {heart_rate:g} bpm.")
    if systolic_bp is not None:
        parts.append(f"Systolic blood pressure {systolic_bp:g} mmHg.")
    if potassium is not None:
        parts.append(f"Serum potassium {potassium:g} mmol/L.")
    if creatinine is not None:
        parts.append(f"Serum creatinine {creatinine:g} mg/dL.")
    if weight_kg is not None:
        parts.append(f"Weight {weight_kg:g} kg.")
    if medications:
        rendered = []
        for med in medications:
            chunk = med["name"]
            if med.get("dose_value") is not None:
                chunk += f" {med['dose_value']:g}"
                if med.get("dose_unit"):
                    chunk += f" {med['dose_unit']}"
            if med.get("frequency"):
                chunk += f" ({med['frequency']})"
            rendered.append(chunk)
        parts.append("Current medications: " + ", ".join(rendered) + ".")
    return " ".join(parts)


def convert_mimic_demo_directory(hosp_dir: Path, *, hf_only: bool = True) -> list[dict]:
    diagnoses_path = hosp_dir / "diagnoses_icd.csv"
    prescriptions_path = hosp_dir / "prescriptions.csv"
    labevents_path = hosp_dir / "labevents.csv"
    chartevents_path = hosp_dir / "chartevents.csv"
    admissions_path = hosp_dir / "admissions.csv"

    required = [prescriptions_path, labevents_path, chartevents_path, admissions_path]
    if any(not path.exists() for path in required):
        missing = [str(path) for path in required if not path.exists()]
        raise FileNotFoundError(f"MIMIC demo hosp tables missing: {', '.join(missing)}")

    hf_hadm = _hf_hadm_ids(diagnoses_path) if hf_only else set()
    prescriptions = _read_csv(prescriptions_path)
    labevents = _read_csv(labevents_path)
    chartevents = _read_csv(chartevents_path)

    labs_by_hadm: dict[int, list[dict[str, str]]] = defaultdict(list)
    for row in labevents:
        labs_by_hadm[int(float(row["hadm_id"]))].append(row)

    charts_by_hadm: dict[int, list[dict[str, str]]] = defaultdict(list)
    for row in chartevents:
        charts_by_hadm[int(float(row["hadm_id"]))].append(row)

    hadm_ids = sorted({int(float(row["hadm_id"])) for row in prescriptions})
    records: list[dict] = []
    for hadm_id in hadm_ids:
        if hf_only and hadm_id not in hf_hadm:
            continue
        medications = _medications_for_hadm(prescriptions, hadm_id)
        if not medications:
            continue
        potassium = _latest_numeric(labs_by_hadm.get(hadm_id, []), POTASSIUM_ITEMIDS)
        creatinine = _latest_numeric(labs_by_hadm.get(hadm_id, []), CREATININE_ITEMIDS)
        heart_rate = _latest_numeric(charts_by_hadm.get(hadm_id, []), HEART_RATE_ITEMIDS)
        systolic_bp = _latest_numeric(charts_by_hadm.get(hadm_id, []), SYSTOLIC_BP_ITEMIDS)
        weight_kg = _latest_numeric(charts_by_hadm.get(hadm_id, []), WEIGHT_ITEMIDS)

        label = empty_intake_label()
        label["potassium"] = potassium
        label["creatinine"] = creatinine
        label["heart_rate"] = heart_rate
        label["systolic_bp"] = systolic_bp
        label["weight_kg"] = weight_kg
        label["conditions"] = ["Heart failure"]
        label["medications"] = medications
        label["chief_complaint"] = "GDMT medication review during heart failure admission."

        note = _render_note(
            heart_rate=heart_rate,
            systolic_bp=systolic_bp,
            potassium=potassium,
            creatinine=creatinine,
            weight_kg=weight_kg,
            medications=medications,
        )
        records.append(to_sft_record(note, label, source=f"mimic_demo:{hadm_id}"))
    return records
