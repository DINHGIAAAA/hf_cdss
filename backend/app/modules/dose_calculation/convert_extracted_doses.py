"""Convert extracted FDA XML drug label data to dose table format.

This module transforms the extracted XML dosing information into the JSON format
used by the dose calculation evaluator.
"""
from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

from app.modules.dose_calculation.xml_dose_extractor import parse_drug_label


# Map drug names to expected drug keys
DRUG_KEY_MAP = {
    "enalapril maleate": "enalapril",
    "enalapril": "enalapril",
    "lisinopril": "lisinopril",
    "lisinopril tablets": "lisinopril",
    "losartan potassium": "losartan",
    "losartan": "losartan",
    "candesartan cilexetil": "candesartan",
    "candesartan": "candesartan",
    "valsartan": "valsartan",
    "sacubitril and valsartan": "sacubitril_valsartan",
    "entresto": "sacubitril_valsartan",
    "spironolactone": "spironolactone",
    "spironolactone tablets": "spironolactone",
    "eplerenone": "eplerenone",
    "inspra": "eplerenone",
    "finerenone": "finerenone",
    "kerendia": "finerenone",
    "metoprolol succinate": "metoprolol_succinate",
    "metoprolol tartrate": "metoprolol_tartrate",
    "lopressor": "metoprolol_tartrate",
    "metoprolol": "metoprolol_succinate",
    "carvedilol": "carvedilol",
    "atenolol": "atenolol",
    "tenormin": "atenolol",
    "propranolol": "propranolol",
    "propranolol hydrochloride": "propranolol",
    "inderal": "propranolol",
    "nebivolol": "nebivolol",
    "bystolic": "nebivolol",
    "ramipril": "ramipril",
    "altace": "ramipril",
    "quinapril": "quinapril",
    "accupril": "quinapril",
    "benazepril": "benazepril",
    "benazepril hydrochloride": "benazepril",
    "lotensin": "benazepril",
    "captopril": "captopril",
    "capoten": "captopril",
    "fosinopril": "fosinopril",
    "fosinopril sodium": "fosinopril",
    "trandolapril": "trandolapril",
    "perindopril": "perindopril",
    "perindopril erbumine": "perindopril",
    "moexipril": "moexipril",
    "moexipril hydrochloride": "moexipril",
    "telmisartan": "telmisartan",
    "micardis": "telmisartan",
    "olmesartan": "olmesartan",
    "olmesartan medoxomil": "olmesartan",
    "benicar": "olmesartan",
    "irbesartan": "irbesartan",
    "avapro": "irbesartan",
    "azilsartan": "azilsartan",
    "azilsartan medoxomil": "azilsartan",
    "edarbi": "azilsartan",
    "canagliflozin": "canagliflozin",
    "invokana": "canagliflozin",
    "ertugliflozin": "ertugliflozin",
    "steglatro": "ertugliflozin",
    "rivaroxaban": "rivaroxaban",
    "xarelto": "rivaroxaban",
    "edoxaban": "edoxaban",
    "savaysa": "edoxaban",
    "dabigatran": "dabigatran",
    "dabigatran etexilate": "dabigatran",
    "pradaxa": "dabigatran",
    "vericiguat": "vericiguat",
    "verquvo": "vericiguat",
    "amiodarone": "amiodarone",
    "amiodarone hydrochloride": "amiodarone",
    "sotalol": "sotalol",
    "dofetilide": "dofetilide",
    "tikosyn": "dofetilide",
    "propafenone": "propafenone",
    "flecainide": "flecainide",
    "flecainide acetate": "flecainide",
    "chlorthalidone": "chlorthalidone",
    "hydrochlorothiazide": "hydrochlorothiazide",
    "ethacrynic acid": "ethacrynic_acid",
    "metformin": "metformin",
    "metformin hydrochloride": "metformin",
    "isosorbide mononitrate": "isosorbide_mononitrate",
    "nitroglycerin": "nitroglycerin",
    "potassium chloride": "potassium_chloride",
    "bidil": "hydralazine_isosorbide",
    "hydralazine hydrochloride and isosorbide dinitrate": "hydralazine_isosorbide",
    "hydralazine and isosorbide dinitrate": "hydralazine_isosorbide",
    "spironolactone and hydrochlorothiazide": "spironolactone_hctz",
    "aldactazide": "spironolactone_hctz",
    "enalapril maleate": "enalapril",
    "losartan potassium": "losartan",
    "candesartan cilexetil": "candesartan",
    "bisoprolol fumarate": "bisoprolol",
    "sacubitril and valsartan": "sacubitril_valsartan",
    "warfarin sodium": "warfarin",
    "dabigatran etexilate": "dabigatran",
    "azilsartan medoxomil": "azilsartan",
    "olmesartan medoxomil": "olmesartan",
    "bisoprolol fumarate": "bisoprolol",
    "bisoprolol": "bisoprolol",
    "digoxin": "digoxin",
    "digoxin tablets": "digoxin",
    "digoxin immune fab": "digoxin_immune_fab",
    "ovine digoxin immune fab": "digoxin_immune_fab",
    "digifab": "digoxin_immune_fab",
    "digibind": "digoxin_immune_fab",
    "dapagliflozin": "dapagliflozin",
    "dapagliflozin tablets": "dapagliflozin",
    "farxiga": "dapagliflozin",
    "empagliflozin": "empagliflozin",
    "empagliflozin tablets": "empagliflozin",
    "jardiance": "empagliflozin",
    "furosemide": "furosemide",
    "furosemide tablets": "furosemide",
    "torsemide": "torsemide",
    "torsemide tablets": "torsemide",
    "bumetanide": "bumetanide",
    "bumetanide tablets": "bumetanide",
    "ivabradine": "ivabradine",
    "ivabradine tablets": "ivabradine",
    "corlanor": "ivabradine",
    "hydralazine hydrochloride": "hydralazine",
    "hydralazine": "hydralazine",
    "isosorbide dinitrate": "isosorbide_dinitrate",
    "isosorbide dinitrate tablets": "isosorbide_dinitrate",
    "warfarin sodium": "warfarin",
    "warfarin": "warfarin",
    "apixaban": "apixaban",
    "apixaban tablets": "apixaban",
    "eliquis": "apixaban",
    "patiromer": "patiromer",
    "patiromer for oral suspension": "patiromer",
    "veltassa": "patiromer",
    "sodium zirconium cyclosilicate": "sodium_zirconium_cyclosilicate",
    "lokelma": "sodium_zirconium_cyclosilicate",
    "metolazone": "metolazone",
    "zaroxolyn": "metolazone",
    "indapamide": "indapamide",
    "acetazolamide": "acetazolamide",
    "diamox": "acetazolamide",
    "tolvaptan": "tolvaptan",
    "samsca": "tolvaptan",
    "sotagliflozin": "sotagliflozin",
    "inpefa": "sotagliflozin",
    "semaglutide": "semaglutide",
    "ozempic": "semaglutide",
    "wegovy": "semaglutide",
    "rybelsus": "semaglutide",
    "tirzepatide": "tirzepatide",
    "mounjaro": "tirzepatide",
    "zepbound": "tirzepatide",
    "dronedarone": "dronedarone",
    "multaq": "dronedarone",
    "mexiletine": "mexiletine",
    "labetalol": "labetalol",
    "magnesium sulfate": "magnesium_sulfate",
    "magnesium oxide": "magnesium_oxide",
    "sodium polystyrene sulfonate": "sodium_polystyrene_sulfonate",
    "kayexalate": "sodium_polystyrene_sulfonate",
    "dobutamine": "dobutamine",
    "milrinone": "milrinone",
    "dopamine": "dopamine",
    "dopamine hydrochloride": "dopamine",
    "norepinephrine": "norepinephrine",
    "norepinephrine bitartrate": "norepinephrine",
    "nitroprusside": "nitroprusside",
    "sodium nitroprusside": "nitroprusside",
    "ferric carboxymaltose": "ferric_carboxymaltose",
    "injectafer": "ferric_carboxymaltose",
    "iron sucrose": "iron_sucrose",
    "venofer": "iron_sucrose",
    "ranolazine": "ranolazine",
    "ranexa": "ranolazine",
    "clonidine": "clonidine",
    "clonidine hydrochloride": "clonidine",
    "aspirin": "aspirin",
    "clopidogrel": "clopidogrel",
    "plavix": "clopidogrel",
    "atorvastatin": "atorvastatin",
    "lipitor": "atorvastatin",
    "rosuvastatin": "rosuvastatin",
    "crestor": "rosuvastatin",
}


# Drug class mapping
DRUG_CLASS_MAP = {
    "enalapril": "ACE Inhibitor",
    "lisinopril": "ACE Inhibitor",
    "ramipril": "ACE Inhibitor",
    "quinapril": "ACE Inhibitor",
    "benazepril": "ACE Inhibitor",
    "captopril": "ACE Inhibitor",
    "fosinopril": "ACE Inhibitor",
    "trandolapril": "ACE Inhibitor",
    "perindopril": "ACE Inhibitor",
    "moexipril": "ACE Inhibitor",
    "candesartan": "ARB",
    "valsartan": "ARB",
    "losartan": "ARB",
    "telmisartan": "ARB",
    "olmesartan": "ARB",
    "irbesartan": "ARB",
    "azilsartan": "ARB",
    "sacubitril_valsartan": "ARNI",
    "spironolactone": "MRA",
    "spironolactone_hctz": "MRA",
    "eplerenone": "MRA",
    "finerenone": "MRA",
    "metoprolol_succinate": "Beta Blocker",
    "metoprolol_tartrate": "Beta Blocker",
    "carvedilol": "Beta Blocker",
    "bisoprolol": "Beta Blocker",
    "atenolol": "Beta Blocker",
    "propranolol": "Beta Blocker",
    "nebivolol": "Beta Blocker",
    "digoxin": "Cardiac Glycoside",
    "digoxin_immune_fab": "Antidote",
    "dapagliflozin": "SGLT2 Inhibitor",
    "empagliflozin": "SGLT2 Inhibitor",
    "canagliflozin": "SGLT2 Inhibitor",
    "ertugliflozin": "SGLT2 Inhibitor",
    "furosemide": "Loop Diuretic",
    "torsemide": "Loop Diuretic",
    "bumetanide": "Loop Diuretic",
    "ethacrynic_acid": "Loop Diuretic",
    "ivabradine": "If Channel Blocker",
    "hydralazine": "Vasodilator",
    "hydralazine_isosorbide": "Vasodilator",
    "isosorbide_dinitrate": "Nitrate",
    "isosorbide_mononitrate": "Nitrate",
    "nitroglycerin": "Nitrate",
    "warfarin": "Anticoagulant",
    "apixaban": "Anticoagulant",
    "rivaroxaban": "Anticoagulant",
    "edoxaban": "Anticoagulant",
    "dabigatran": "Anticoagulant",
    "vericiguat": "sGC Stimulator",
    "amiodarone": "Antiarrhythmic",
    "sotalol": "Antiarrhythmic",
    "dofetilide": "Antiarrhythmic",
    "propafenone": "Antiarrhythmic",
    "flecainide": "Antiarrhythmic",
    "chlorthalidone": "Thiazide Diuretic",
    "hydrochlorothiazide": "Thiazide Diuretic",
    "metformin": "Diabetes",
    "potassium_chloride": "Electrolyte",
    "patiromer": "Potassium Binder",
    "sodium_zirconium_cyclosilicate": "Potassium Binder",
    "sodium_polystyrene_sulfonate": "Potassium Binder",
    "metolazone": "Thiazide Diuretic",
    "indapamide": "Thiazide Diuretic",
    "acetazolamide": "Diuretic Adjunct",
    "tolvaptan": "Vasopressin Antagonist",
    "sotagliflozin": "SGLT2 Inhibitor",
    "semaglutide": "GLP-1 RA",
    "tirzepatide": "GLP-1 RA",
    "dronedarone": "Antiarrhythmic",
    "mexiletine": "Antiarrhythmic",
    "labetalol": "Beta Blocker",
    "magnesium_sulfate": "Electrolyte",
    "magnesium_oxide": "Electrolyte",
    "dobutamine": "Inotrope",
    "milrinone": "Inotrope",
    "dopamine": "Inotrope",
    "norepinephrine": "Vasopressor",
    "nitroprusside": "Vasodilator",
    "ferric_carboxymaltose": "Iron Therapy",
    "iron_sucrose": "Iron Therapy",
    "ranolazine": "Antianginal",
    "clonidine": "Antihypertensive",
    "aspirin": "Antiplatelet",
    "clopidogrel": "Antiplatelet",
    "atorvastatin": "Statin",
    "rosuvastatin": "Statin",
}


def normalize_drug_name(name: str) -> str:
    """Normalize drug name to extract key."""
    name_lower = name.lower().strip()

    # Try exact match first
    if name_lower in DRUG_KEY_MAP:
        return DRUG_KEY_MAP[name_lower]

    # Prefer longest partial match (e.g. metoprolol tartrate over metoprolol)
    partial = [
        (key, value)
        for key, value in DRUG_KEY_MAP.items()
        if key in name_lower or name_lower in key
    ]
    if partial:
        return max(partial, key=lambda item: len(item[0]))[1]

    # Fall back to drug_aliases.json (exact brand/generic → pipeline_id)
    aliases = _load_drug_aliases()
    for pipeline_id, entry in aliases.items():
        tokens = {
            pipeline_id.replace("_", " "),
            str(entry.get("display_name") or "").lower(),
            *[
                str(a).lower()
                for a in (entry.get("aliases") or [])
                if a and not any(ch.isdigit() for ch in str(a))
            ],
        }
        tokens = {t.strip() for t in tokens if t and t.strip()}
        if name_lower in tokens:
            return pipeline_id

    return name_lower.replace(" ", "_").replace("-", "_")


@lru_cache(maxsize=1)
def _load_drug_aliases() -> dict[str, Any]:
    path = Path("data/heart_failure/config/drug_aliases.json")
    if not path.is_file():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


_CLASS_LABELS = {
    "ACEi": "ACE Inhibitor",
    "ARB": "ARB",
    "ARNI": "ARNI",
    "MRA": "MRA",
    "beta_blocker": "Beta Blocker",
    "SGLT2i": "SGLT2 Inhibitor",
    "loop_diuretic": "Loop Diuretic",
    "thiazide_diuretic": "Thiazide Diuretic",
    "anticoagulant": "Anticoagulant",
    "antiarrhythmic": "Antiarrhythmic",
    "vasodilator": "Vasodilator",
    "vasodilator_combo": "Vasodilator",
    "cardiac_glycoside": "Cardiac Glycoside",
    "heart_rate_reducing": "If Channel Blocker",
    "sGC_stimulator": "sGC Stimulator",
    "calcium_channel_blocker": "Calcium Channel Blocker",
    "antiplatelet": "Antiplatelet",
    "statin": "Statin",
    "lipid_lowering": "Lipid Lowering",
    "pcsk9_inhibitor": "PCSK9 Inhibitor",
    "fibrate": "Fibrate",
    "thrombolytic": "Thrombolytic",
    "vasopressor": "Vasopressor",
    "inotrope": "Inotrope",
    "pah_therapy": "PAH Therapy",
    "alpha_blocker": "Alpha Blocker",
    "potassium_sparing_diuretic": "Potassium-Sparing Diuretic",
    "osmotic_diuretic": "Osmotic Diuretic",
    "antidote": "Antidote",
    "anti_inflammatory_cv": "Anti-inflammatory CV",
    "electrolyte": "Electrolyte",
    "potassium_binder": "Potassium Binder",
    "GLP1_RA": "GLP-1 RA",
    "iron_therapy": "Iron Therapy",
    "diuretic_adjunct": "Diuretic Adjunct",
    "vasopressin_antagonist": "Vasopressin Antagonist",
    "antianginal": "Antianginal",
    "antihypertensive": "Antihypertensive",
    "diabetes": "Diabetes",
}


def class_for_drug_key(drug_key: str) -> str:
    if drug_key in DRUG_CLASS_MAP:
        return DRUG_CLASS_MAP[drug_key]
    aliases = _load_drug_aliases()
    entry = aliases.get(drug_key) or {}
    raw = str(entry.get("gdmt_class") or "")
    if raw in _CLASS_LABELS:
        return _CLASS_LABELS[raw]
    # Also try matching normalize of folder-like keys
    for pid, ent in aliases.items():
        if normalize_drug_name(pid.replace("_", " ")) == drug_key:
            return _CLASS_LABELS.get(str(ent.get("gdmt_class") or ""), "Unknown")
    return "Unknown"


def _tables_as_text(tables: list[dict] | None) -> str:
    """Flatten table rows into searchable text."""
    if not tables:
        return ""
    parts: list[str] = []
    for table in tables:
        for row in table.get("rows") or []:
            parts.append(" | ".join(row))
    return " ".join(parts)


def _parse_egfr_token(token: str) -> tuple[float | None, float | None]:
    """Parse eGFR/CrCl cell text into (min, max)."""
    t = token.replace("≥", ">=").replace("≤", "<=").replace("–", "-").replace("—", "-")
    t = re.sub(r"\s+", " ", t).strip()

    m = re.search(r">=\s*(\d+(?:\.\d+)?)\s*to\s*<\s*(\d+(?:\.\d+)?)", t, re.I)
    if m:
        return float(m.group(1)), float(m.group(2))
    m = re.search(r">=\s*(\d+(?:\.\d+)?)\s*-\s*<\s*(\d+(?:\.\d+)?)", t, re.I)
    if m:
        return float(m.group(1)), float(m.group(2))
    m = re.search(r">=\s*(\d+(?:\.\d+)?)", t)
    if m:
        return float(m.group(1)), None
    m = re.search(r">\s*(\d+(?:\.\d+)?)", t)
    if m:
        return float(m.group(1)), None
    m = re.search(r"<\s*(\d+(?:\.\d+)?)", t)
    if m:
        return None, float(m.group(1))
    m = re.search(r"<=\s*(\d+(?:\.\d+)?)", t)
    if m:
        return None, float(m.group(1))
    m = re.search(r"(\d+(?:\.\d+)?)\s*(?:to|-)\s*(\d+(?:\.\d+)?)", t, re.I)
    if m:
        return float(m.group(1)), float(m.group(2))
    return None, None


def _parse_dose_cell(cell: str) -> dict[str, Any] | None:
    """Parse a dose cell like '20 mg orally once daily' or 'Initiation is not recommended'."""
    low = cell.lower()
    if any(t in low for t in ("not recommended", "do not", "avoid", "contraindic")):
        return {"adjustment": "avoid", "dose": None, "note": cell.strip()}

    m = re.search(
        r"(\d+(?:\.\d+)?)(?:/\d+(?:\.\d+)?)?\s*(mg|mcg|g)\b"
        r"(?:[^.]{0,40}?\b(once|twice|three times)\s*(?:daily|a day|a day))?",
        cell,
        re.I,
    )
    if not m:
        return None
    freq = None
    if m.lastindex and m.lastindex >= 3 and m.group(3):
        word = m.group(3).lower()
        freq = {
            "once": "once daily",
            "twice": "twice daily",
            "three times": "three times daily",
        }.get(word)
    return {
        "dose": float(m.group(1)),
        "dose_unit": m.group(2).lower(),
        "frequency": freq,
        "adjustment": "reduce",
        "note": cell.strip(),
    }


def extract_dosing_from_tables(tables: list[dict] | None) -> dict[str, Any]:
    """Extract starting/target doses and eGFR bands from dosage tables."""
    result: dict[str, Any] = {
        "starting_dose": None,
        "target_dose": None,
        "max_dose": None,
        "frequency": None,
        "dose_unit": None,
        "egfr_adjustments": [],
        "potassium_adjustments": [],
    }
    if not tables:
        return result

    for table in tables:
        rows = table.get("rows") or []
        if len(rows) < 2:
            continue
        header = " ".join(rows[0]).lower()

        # Digoxin-style mcg/kg maintenance/loading
        if "mcg/kg" in header or any("mcg/kg" in " ".join(r).lower() for r in rows[:2]):
            for row in rows[1:]:
                joined = " ".join(row).lower()
                if "adult" not in joined:
                    continue
                m = re.search(r"(\d+(?:\.\d+)?)\s*to\s*(\d+(?:\.\d+)?)", " ".join(row), re.I)
                if m:
                    result["starting_dose"] = float(m.group(1))
                    result["target_dose"] = float(m.group(2))
                    result["dose_unit"] = "mcg/kg"
                    result["frequency"] = "once daily"
                    break

        # Starting dose by eGFR (finerenone Table 1)
        if "egfr" in header and ("starting" in header or "dose" in header):
            preferred_start = None
            for row in rows[1:]:
                if len(row) < 2:
                    continue
                egfr_min, egfr_max = _parse_egfr_token(row[0])
                parsed = _parse_dose_cell(row[1])
                if not parsed:
                    continue
                if parsed.get("adjustment") == "avoid":
                    result["egfr_adjustments"].append({
                        "egfr_min": egfr_min,
                        "egfr_max": egfr_max if egfr_max is not None else (
                            float(re.search(r"(\d+)", row[0]).group(1))
                            if re.search(r"(\d+)", row[0]) else None
                        ),
                        "dose": None,
                        "adjustment": "avoid",
                        "note": parsed["note"],
                    })
                    continue
                result["egfr_adjustments"].append({
                    "egfr_min": egfr_min,
                    "egfr_max": egfr_max,
                    "dose": parsed["dose"],
                    "adjustment": "reduce" if (
                        egfr_max is not None or (egfr_min is not None and egfr_min < 60)
                    ) else "none",
                    "note": parsed["note"],
                    "frequency": parsed.get("frequency"),
                })
                if egfr_min is not None and egfr_min >= 60:
                    preferred_start = parsed
                elif preferred_start is None:
                    preferred_start = parsed
            if preferred_start and result["starting_dose"] is None:
                result["starting_dose"] = preferred_start["dose"]
                result["dose_unit"] = preferred_start.get("dose_unit")
                result["frequency"] = preferred_start.get("frequency")

        # Indication × dose tables (empagliflozin)
        if "indication" in header and ("dose" in header or "dosage" in header):
            hf_parsed = None
            any_adult = None
            for row in rows[1:]:
                joined = " ".join(row).lower()
                parsed = None
                for cell in row:
                    parsed = _parse_dose_cell(cell)
                    if parsed and parsed.get("dose") is not None:
                        break
                if not parsed or parsed.get("dose") is None:
                    continue
                if "heart failure" in joined or "hospitalization in patients with heart failure" in joined:
                    hf_parsed = parsed
                elif "adult" in joined or len(row) >= 3:
                    any_adult = any_adult or parsed
            chosen = hf_parsed or any_adult
            if chosen and result["starting_dose"] is None:
                result["starting_dose"] = chosen["dose"]
                result["dose_unit"] = chosen.get("dose_unit")
                result["frequency"] = chosen.get("frequency")
                result["target_dose"] = chosen["dose"]

        # Warfarin genotype table: take common GG/*1/*1 range mid/low
        if "vkorn" in header.replace("c", "") or "cyp2c9" in header or (
            any("vkorn" in " ".join(r).lower().replace("c", "") or "cyp2c9" in " ".join(r).lower() for r in rows[:2])
        ):
            for row in rows[1:]:
                if not row or row[0].upper() not in {"GG", "AG", "AA"}:
                    continue
                if row[0].upper() != "GG":
                    continue
                m = re.search(r"(\d+(?:\.\d+)?)\s*to\s*(\d+(?:\.\d+)?)\s*mg", " ".join(row), re.I)
                if m and result["starting_dose"] is None:
                    result["starting_dose"] = float(m.group(1))
                    result["target_dose"] = float(m.group(2))
                    result["dose_unit"] = "mg"
                    result["frequency"] = "once daily"
                    break

        # Potassium adjustment tables (finerenone monitoring)
        if "potassium" in header or any("potassium" in " ".join(r).lower() for r in rows[:3]):
            for row in rows[1:]:
                if not row:
                    continue
                k_cell = row[0]
                if not re.search(r"\d", k_cell):
                    continue
                k_min, k_max = _parse_egfr_token(k_cell)
                action_text = " ".join(row[1:]).lower()
                if "withhold" in action_text or "interrupt" in action_text:
                    adj = "avoid" if (k_min and k_min >= 6.0) or "6.0" in k_cell else "reduce_or_hold"
                elif "increase" in action_text:
                    continue
                elif "maintain" in action_text or "decrease" in action_text:
                    adj = "caution"
                else:
                    continue
                thr = k_min if k_min is not None else k_max
                if thr is None:
                    continue
                result["potassium_adjustments"].append({
                    "k_min": k_min if k_min is not None else thr,
                    "k_max": k_max,
                    "adjustment": adj,
                    "note": " ".join(row)[:180],
                    "source": "fda_xml_table",
                })

    return result


def extract_dosing_from_section(section: dict) -> dict[str, Any]:
    """Extract dosing information from a dosage section (text + tables)."""
    result = {
        "starting_dose": None,
        "target_dose": None,
        "max_dose": None,
        "frequency": None,
        "route": "oral",
        "dose_unit": None,
        "egfr_adjustments": [],
        "potassium_adjustments": [],
        "loading_dose": None,
    }

    content = section.get("content", "") or ""
    table_text = _tables_as_text(section.get("tables"))
    title = section.get("title") or ""
    blob = _normalize_ws(f"{title} {content} {table_text}")
    # Normalize thousand separators: 5,000 -> 5000
    blob_num = re.sub(r"(?<=\d),(?=\d{3}\b)", "", blob)

    table_dosing = extract_dosing_from_tables(section.get("tables"))
    for key in ("starting_dose", "target_dose", "max_dose", "frequency", "dose_unit"):
        if table_dosing.get(key) is not None and result.get(key) is None:
            result[key] = table_dosing[key]
    result["egfr_adjustments"] = table_dosing.get("egfr_adjustments") or []
    result["potassium_adjustments"] = table_dosing.get("potassium_adjustments") or []

    if len(blob_num) < 20 and result["starting_dose"] is None:
        return result

    low = blob_num.lower()
    if any(t in low for t in ("intravenous", " i.v.", " iv ", "infusion", "bolus")):
        result["route"] = "intravenous"
    elif any(t in low for t in ("subcutaneous", " s.c.", " subcut")):
        result["route"] = "subcutaneous"
    elif "inhal" in low:
        result["route"] = "inhalation"

    starting_patterns = [
        # Loading then maintenance -> prefer maintenance as chronic starting dose
        r"(?:loading dose|single\s+\d+(?:\.\d+)?\s*mg\s+oral\s+loading dose).{0,100}?"
        r"(?:continue(?:\s+at)?|then|followed by)\s*(?:at\s*)?(\d+(?:\.\d+)?)\s*(mg|mcg|g)\b",
        r"continue(?:\s+at)?\s*(\d+(?:\.\d+)?)\s*(mg|mcg|g)\s*(?:once\s+daily|orally\s+once\s+daily|daily|orally)",
        r"(?:then|followed by)\s*(?:continue(?:\s+at)?\s*)?(\d+(?:\.\d+)?)\s*(mg|mcg|g)\s*(?:once\s+daily|daily)",
        r"(?:recent mi|peripheral arterial disease|established peripheral)[^.]{0,80}?"
        r"(\d+(?:\.\d+)?)\s*(mg)\s+once daily",
        # Explicit loading / initiate
        r"(?:loading\s+dose(?:\s+of)?|initiate(?:\s+\w+){0,8}\s+with\s+a\s+single)\s*"
        r"(\d+(?:\.\d+)?)\s*(mg|mcg|g|units?)\b",
        r"loading doses?\s+of\s+(\d+(?:\.\d+)?)\s*(?:to|-)\s*(\d+(?:\.\d+)?)\s*(mg|mcg|g)(?:/day)?",
        r"initiate(?:\s+\w+){0,10}\s+(?:treatment\s+)?(?:as\s+)?(?:a\s+)?(?:single\s+)?"
        r"(\d+(?:\.\d+)?)\s*(mg|mcg|g|units?)\b",
        r"initiate(?:\s+treatment)?\s+(?:with|at)\s+(?:a\s+)?(?:loading\s+doses?\s+of\s+)?"
        r"(\d+(?:\.\d+)?)(?:\s*(?:to|-)\s*(\d+(?:\.\d+)?))?\s*(mg|mcg|g)(?:/day)?",
        r"for continued treatment[^.]{0,100}?(\d+(?:\.\d+)?)\s*(g|mg)\s+(?:once\s+daily|daily)",
        r"(?:recommended\s+)?maintenance(?:\s+dose)?[^.]{0,80}?(\d+(?:\.\d+)?)\s*(g|mg)\s+once\s+daily",
        r"usual adult dos(?:e|age)\s*:\s*(\d+(?:\.\d+)?)\s*(mg|mcg|g|units?)\b(?!\s*/\s*kg)",
        r"recommended starting dos(?:e|age)\b.{0,160}?\b(?:is|are|:)\s*"
        r"(\d+(?:\.\d+)?)(?:/\d+(?:\.\d+)?)?\s*(mg|mcg|g)\b(?!\s*/\s*kg)",
        r"recommended(?:\s+initial)?\s+dos(?:e|age)\b.{0,140}?\b(?:is|are|:)\s*"
        r"(\d+(?:\.\d+)?)(?:/\d+(?:\.\d+)?)?\s*(mg|mcg|g|units?|mg/kg|mcg/kg|mg/kg/h|mcg/kg/min)\b",
        r"the recommended dos(?:e|age)\s+is\s+(?:a\s+)?"
        r"(\d+(?:\.\d+)?)\s*(mg|mcg|g|units?|mg/kg|mcg/kg|mg/kg/h|mcg/kg/min)\b",
        r"recommended initial dose(?:\s+for treating heart failure)?\s+is\s+(\d+(?:\.\d+)?)\s*(mg|mcg|g)",
        r"usual initial dose\b.{0,60}?\bis\s+(\d+(?:\.\d+)?)(?:\s*to\s*(\d+(?:\.\d+)?))?\s*(mg|mcg|g)\b",
        r"starting dos(?:e|age)\b.{0,120}?\b(?:is|are|:)\s*"
        r"(\d+(?:\.\d+)?)(?:/\d+(?:\.\d+)?)?\s*(mg|mcg|g|units?)\b(?!\s*/\s*kg)",
        r"initial dose\s*(?:of|:)?\s*(\d+(?:\.\d+)?)\s*(mg|mcg|g|units?)\b",
        r"start with\s+(\d+(?:\.\d+)?)\s*(mg|mcg|g)",
        r"starting dose[:\s]*(\d+(?:\.\d+)?)\s*(mg)\b(?!\s*/\s*kg)",
        # Range forms commonly used in diuretic/antiarrhythmic labels
        r"(?:usual(?:\s+total)?(?:\s+daily)?\s+dos(?:e|age)|daily dosage|dosage of \w+)\s+is\s+"
        r"(\d+(?:\.\d+)?)\s*(mg|mcg|g|mEq|meq|grams?)\s*(?:to|-)\s*(\d+(?:\.\d+)?)\s*(?:mg|mcg|g|mEq|meq|grams?)?",
        r"(?:usual(?:\s+total)?(?:\s+daily)?\s+dos(?:e|age)|daily dose)\s+(?:of \w+\s+)?is\s+"
        r"(\d+(?:\.\d+)?)\s*(mg|mcg|g|mEq|meq|grams?|gram)\b",
        r"(?:daily dose|dose)\s+of\s+\w+\s+is\s+(\d+(?:\.\d+)?)\s*(mg|mcg|g|grams?|gram|mEq|meq)\b",
        r"(\d+(?:\.\d+)?)\s*(?:to|-)\s*(\d+(?:\.\d+)?)\s*(mg|mcg|g|mEq|meq)\s+"
        r"(?:once daily|twice daily|daily|/day|and in most patients)\b",
        r"(?:start|starting dosage|recommended starting dosage)\s+\w*\s*(?:intravenously\s+)?at\s+"
        r"(\d+(?:\.\d+)?)\s*(nanograms?|ng|mcg|mg)\s*(?:\(\s*ng\s*\))?\s*/\s*kg\s*/\s*min",
        r"(\d+(?:\.\d+)?)\s*(nanograms?|ng)\s*(?:\(\s*ng\s*\))?\s*/\s*kg\s*/\s*min",
        r"(\d+(?:\.\d+)?)\s*(grams?|gram|g)\s+per\s+day",
        r"(?:typically in the range of|prevention of hypokalemia is typically)\s*"
        r"(\d+(?:\.\d+)?)\s*(mEq|meq)\b",
        r"doses of\s+(\d+(?:\.\d+)?)\s*(mEq|meq)\s*(?:to|-)\s*(\d+(?:\.\d+)?)\s*(mEq|meq)?",
        r"(?:take|administer)\s+(\d+|one|two|three)\s+or\s+(\d+|two|three)\s+tablets?",
        r"(?:take|administer)\s+(one|1|two|2|three|3)\s+tablets?",
        r"(?:one|1)\s+tablet\s+under the tongue",
        r"(?:usual dose is\s+)?one drop\b",
        r"one additional tablet may be administered",
        # Weight-based
        r"(?:bolus(?:\s+dose)?|intravenous bolus)\s*(?:of\s+|dose\s+of\s+)?"
        r"(\d+(?:\.\d+)?)\s*(mg/kg|mcg/kg)\b",
        r"(?:infusion|maintenance infusion)\s*(?:of\s+|rate\s+of\s+)?"
        r"(\d+(?:\.\d+)?)\s*(mg/kg/h|mcg/kg/min|mcg/kg/h)\b",
        r"(\d+(?:\.\d+)?)\s*(?:to|-)\s*(\d+(?:\.\d+)?)\s*"
        r"(mcg/kg/min|mg/kg/min|mcg/kg/h|mg/kg/h|mcg/kg|mg/kg)\b",
        r"(?:recommended\s+)?(?:starting\s+)?maintenance dose.{0,100}?"
        r"(\d+(?:\.\d+)?)\s*(?:to|-)\s*(\d+(?:\.\d+)?)\s*(mcg/kg|mg/kg)",
        # Units
        r"initial dose\s*(\d+(?:\.\d+)?)\s*(units?)\b",
        r"(\d+(?:\.\d+)?)\s*(units?)\s+by\s+intravenous",
        r"(\d+(?:\.\d+)?)\s*(units?)/kg\b",
        # Tablet-count products (e.g., BiDil)
        r"initiated at a dose of\s+(?:one|1)\s+\w+\s+tablet",
        r"one\s+\w+\s+tablet,\s*three times",
    ]

    WORD_NUM = {"one": 1.0, "two": 2.0, "three": 3.0, "four": 4.0, "1": 1.0, "2": 2.0, "3": 3.0, "4": 4.0}

    def _to_num(value: str | None) -> float | None:
        if value is None:
            return None
        raw = value.lower().strip()
        if raw in WORD_NUM:
            return WORD_NUM[raw]
        try:
            return float(raw)
        except ValueError:
            return None

    def _norm_unit(raw: str | None) -> str | None:
        if not raw:
            return None
        u = raw.lower()
        u = u.replace("nanograms", "ng").replace("nanogram", "ng")
        u = u.replace("grams", "g").replace("gram", "g")
        if u.startswith("unit"):
            return "units"
        if u == "meq":
            return "mEq"
        return u

    for pattern in starting_patterns:
        match = re.search(pattern, blob_num, re.IGNORECASE)
        if not match:
            continue
        around = blob_num[max(0, match.start() - 40): match.end() + 40].lower()
        if "pediatric" in around and "adult" not in around:
            continue

        g0 = match.group(0).lower()

        # Drop / tablet-count products without numeric capture groups
        if re.search(r"\bdrop\b", g0) and (not match.lastindex or match.lastindex == 0):
            result["starting_dose"] = 1.0
            result["dose_unit"] = "drop"
            result["frequency"] = result.get("frequency") or "twice daily"
            result["route"] = "ophthalmic"
            break
        if re.search(r"\btablet", g0) and (not match.lastindex):
            result["starting_dose"] = 1.0
            result["dose_unit"] = "tablet"
            if "three times" in g0 or "three times" in low:
                result["frequency"] = "three times daily"
            if "every 4 hours" in low:
                result["frequency"] = "every 4 hours"
            mmax = re.search(
                r"(?:not to exceed|no more than|maximum(?:\s+of)?)\s+(\d+|two|three|twelve)\s+tablets?",
                blob_num,
                re.I,
            )
            if mmax:
                result["max_dose"] = _to_num(mmax.group(1))
            elif re.search(r"maximum of\s+(?:two|2)\s+tablets?", blob_num, re.I):
                result["target_dose"] = 2.0
                result["max_dose"] = 2.0
            break

        # Tablet with word/number captures: take 1 or 2 tablets / take one tablet
        if re.search(r"\btablet", g0) and match.lastindex:
            a = _to_num(match.group(1))
            b = _to_num(match.group(2)) if match.lastindex >= 2 else None
            if a is not None:
                result["starting_dose"] = a
                result["dose_unit"] = "tablet"
                if b is not None:
                    result["target_dose"] = b
                    result["max_dose"] = b
                if "every 4 hours" in low:
                    result["frequency"] = "every 4 hours"
                elif "every 5 minutes" in low:
                    result["frequency"] = "every 5 minutes"
                break

        # ng/kg/min and similar
        if "/kg/min" in g0.replace(" ", "") or "ng)/kg/min" in g0.replace(" ", ""):
            nums = [float(x) for x in re.findall(r"\d+(?:\.\d+)?", match.group(0))]
            if nums:
                result["starting_dose"] = nums[0]
                result["dose_unit"] = "ng/kg/min"
                result["route"] = "intravenous"
                break

        if any(u in g0 for u in ("mg/kg", "mcg/kg", "units/kg", "ng/kg")):
            nums = [float(x) for x in re.findall(r"\d+(?:\.\d+)?", match.group(0))]
            unit = None
            for i in range(1, (match.lastindex or 0) + 1):
                g = match.group(i)
                if g and "kg" in g.lower():
                    unit = _norm_unit(g)
            if unit is None:
                for cand in (
                    "ng/kg/min",
                    "mcg/kg/min",
                    "mg/kg/min",
                    "mcg/kg/h",
                    "mg/kg/h",
                    "mg/kg",
                    "mcg/kg",
                    "units/kg",
                ):
                    if cand in g0.replace(" ", ""):
                        unit = cand
                        break
            if nums:
                result["starting_dose"] = nums[0]
                if len(nums) >= 2:
                    result["target_dose"] = nums[1]
                    result["max_dose"] = nums[1]
                if unit:
                    result["dose_unit"] = unit
                break

        if "loading" in g0 and match.lastindex and match.lastindex >= 3:
            try:
                low_v = float(match.group(1))
                high_v = float(match.group(2)) if match.group(2) else None
                unit = _norm_unit(match.group(match.lastindex) or "mg")
                result["loading_dose"] = low_v
                result["starting_dose"] = low_v
                if high_v is not None:
                    result["target_dose"] = high_v
                    result["max_dose"] = high_v
                result["dose_unit"] = unit
                break
            except (TypeError, ValueError):
                pass

        try:
            result["starting_dose"] = float(match.group(1))
        except (TypeError, ValueError, IndexError):
            # Maybe group1 is a word number for tablets already handled
            n = _to_num(match.group(1)) if match.lastindex and match.lastindex >= 1 else None
            if n is None:
                continue
            result["starting_dose"] = n

        unit = None
        high = None
        for i in range(2, (match.lastindex or 1) + 1):
            g = match.group(i)
            if g is None:
                continue
            if re.fullmatch(r"\d+(?:\.\d+)?", g):
                high = float(g)
            elif re.fullmatch(
                r"mg|mcg|g|grams?|gram|units?|mEq|meq|ng|nanograms?|"
                r"mg/kg|mcg/kg|mg/kg/h|mcg/kg/min|mcg/kg/h|units?/kg|ng/kg/min",
                g,
                re.I,
            ):
                unit = _norm_unit(g)
        if unit:
            result["dose_unit"] = unit
        if high is not None:
            result["target_dose"] = high
            result["max_dose"] = high
        if "loading" in g0 and result.get("loading_dose") is None:
            result["loading_dose"] = result["starting_dose"]
        break

    # Generic fallback: first plausible adult numeric dose in section text
    if result["starting_dose"] is None:
        for generic in re.finditer(
            r"(?<!/)\b(\d+(?:\.\d+)?)\s*(mg|mcg|g|units?|mEq|meq|grams?|gram|ng)\b"
            r"(?!\s*/\s*kg)(?:\s*(?:to|-)\s*(\d+(?:\.\d+)?)\s*(?:mg|mcg|g|units?|mEq|meq|grams?|gram))?"
            r"(?:\s*(?:once daily|twice daily|daily|/day|orally|per day))?",
            blob_num,
            re.I,
        ):
            around = blob_num[max(0, generic.start() - 50): generic.end() + 30].lower()
            if any(
                t in around
                for t in ("pediatric", "child", "infant", "neonat", " years of age", "year of age")
            ) and "adult" not in around:
                continue
            if re.search(r"\b\d+\s*years?\b", around) and "adult" not in around:
                continue
            if "maximum" in around and "initial" not in around and "starting" not in around:
                continue
            result["starting_dose"] = float(generic.group(1))
            unit = generic.group(2).lower()
            if unit.startswith("unit"):
                result["dose_unit"] = "units"
            elif unit in {"gram", "grams"}:
                result["dose_unit"] = "g"
            elif unit == "meq":
                result["dose_unit"] = "mEq"
            else:
                result["dose_unit"] = unit
            if generic.group(3):
                result["target_dose"] = float(generic.group(3))
                result["max_dose"] = float(generic.group(3))
            break

        if result["starting_dose"] is None:
            # OTC tablet directions / SL nitroglycerin
            mtab = re.search(
                r"(?:take|administer)\s+(\d+|one|two|three)\s+or\s+(\d+|two|three)\s+tablets?"
                r"|(?:take|administer)\s+(one|1|two|2)\s+(?:or two\s+)?(?:antacid\s+)?tablets?"
                r"|(?:one|1)\s+tablet\s+under the tongue"
                r"|one drop of",
                blob_num,
                re.I,
            )
            if mtab:
                g0 = mtab.group(0).lower()
                if "drop" in g0:
                    result["starting_dose"] = 1.0
                    result["dose_unit"] = "drop"
                else:
                    nums = []
                    for i in range(1, (mtab.lastindex or 0) + 1):
                        n = None
                        if mtab.group(i):
                            raw = mtab.group(i).lower()
                            n = {"one": 1.0, "two": 2.0, "three": 3.0}.get(raw)
                            if n is None:
                                try:
                                    n = float(raw)
                                except ValueError:
                                    n = None
                        if n is not None:
                            nums.append(n)
                    result["starting_dose"] = nums[0] if nums else 1.0
                    result["dose_unit"] = "tablet"
                    if len(nums) > 1:
                        result["target_dose"] = nums[1]
                        result["max_dose"] = nums[1]


    target_patterns = [
        r"target(?:\s+maintenance)?\s+dose\s*(?:of|:|is)?\s*(\d+(?:\.\d+)?(?:/\d+(?:\.\d+)?)?)\s*(mg|mcg|g)?",
        r"(?:increased?|uptitrat\w*|titrate\w*|doubling the dose).*?(?:to\s+)?(?:the\s+)?"
        r"(?:target dose of\s+)?(\d+(?:\.\d+)?)\s*(mg|mcg|g)",
        r"up to\s+(?:a\s+)?(?:maximum\s+dose\s+of\s+)?(\d+(?:\.\d+)?)\s*(mg|mcg|g|grams?)",
        r"maximum dose\s*(?:of|:)?\s*(\d+(?:\.\d+)?)\s*(mg|mcg|g|grams?)",
        r"may increase to\s+(\d+(?:\.\d+)?)\s*(mg|mcg|g)",
        r"titrate to a maximum of\s+(?:two|2)\s+tablets?",
        r"maximum of\s+(?:two|2)\s+tablets?",
        r"continue at\s+(\d+(?:\.\d+)?)\s*(mg|mcg|g)",
    ]
    section_title = (section.get("title") or "").lower()
    is_hf_section = "heart failure" in section_title or "hf" in section_title.split()

    for pattern in target_patterns:
        match = re.search(pattern, blob_num, re.IGNORECASE)
        if not match:
            continue
        if "tablet" in match.group(0).lower():
            result["target_dose"] = 2.0
            result["max_dose"] = 2.0
            result["dose_unit"] = result.get("dose_unit") or "tablet"
            break
        raw_val = match.group(1)
        if raw_val is None:
            continue
        if "/" in raw_val:
            raw_val = raw_val.split("/")[0]
        try:
            val = float(raw_val)
        except (ValueError, TypeError):
            continue
        unit = None
        if match.lastindex and match.lastindex >= 2 and match.group(2):
            unit = match.group(2).lower().replace("grams", "g").replace("gram", "g")
        if "maximum" in match.group(0).lower() or "up to" in match.group(0).lower():
            result["max_dose"] = val
            if result["target_dose"] is None and (is_hf_section or True):
                result["target_dose"] = val
        else:
            result["target_dose"] = val
        if unit and not result.get("dose_unit"):
            result["dose_unit"] = unit
        break

    if result["target_dose"] is None and result["max_dose"]:
        result["target_dose"] = result["max_dose"]

    freq_patterns = [
        r"(once|twice|three times|four times)\s*(?:a |per )?day",
        r"(once|twice)\s*daily",
        r"four times daily",
        r"three times(?:\s+a\s+day|\s+daily)",
        r"(\d+)\s*(?:times|×)\s*a\s*day",
        r"every\s*other\s*day",
    ]
    for pattern in freq_patterns:
        match = re.search(pattern, blob_num, re.IGNORECASE)
        if match:
            freq = match.group(0).lower()
            if "every other" in freq:
                result["frequency"] = "every other day"
            elif "four" in freq or "4 times" in freq:
                result["frequency"] = "four times daily"
            elif "three" in freq or "3 times" in freq:
                result["frequency"] = "three times daily"
            elif "once" in freq:
                result["frequency"] = "once daily"
            elif "twice" in freq or "2 times" in freq:
                result["frequency"] = "twice daily"
            break

    return result


def _normalize_ws(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def _select_dosage_section(dosage_sections: list[dict]) -> dict | None:
    """Prefer adult heart-failure dosing subsection over parent/hypertension text."""
    if not dosage_sections:
        return None

    parent = dosage_sections[0]
    subsections = parent.get("subsections") or []

    def _score(section: dict) -> tuple[int, int]:
        title = (section.get("title") or "").lower()
        content = section.get("content") or ""
        tables = section.get("tables") or []
        blob = f"{content} {_tables_as_text(tables)}".lower()
        score = 0

        # Strong preference for HF-titled dosing
        if "heart failure" in title:
            score += 120
        if "adult heart failure" in title or re.search(r"\bhf\b", title):
            score += 30
        if "treatment of heart failure" in title:
            score += 20
        if "heart failure post" in title or "post-myocardial" in title or "post-mi" in title:
            score += 40
        if "left ventricular" in title:
            score += 45

        # Adult maintenance / recommended dose (neutral indications)
        if "maintenance dosing in adults" in title:
            score += 80
        if "recommended starting" in title or "recommended dose" in title:
            score += 55
        if "recommended dosage" in title and "glycemic" not in title and "other indication" not in title:
            score += 50
        if "oral administration" in title:
            score += 40
        if "initial and maintenance" in title:
            score += 35
        if "adult patients" in title:
            score += 50
        if tables:
            score += 25

        # Content signals
        if "heart failure" in blob:
            score += 50
        if re.search(r"\b(nyha|hfref|hfpef|reduced ejection)\b", blob):
            score += 25
        # Anticoagulant adult AF dosing (apixaban NVAF 5 mg)
        if "atrial fibrillation" in title or "nonvalvular" in title:
            score += 90
        if "atrial fibrillation" in blob and "recommended dose" in blob:
            score += 40
        if "usual adult dose" in blob:
            score += 50
        if re.search(
            r"(starting dos(?:e|age)|initiate(?:\s+treatment)?\s+at|initial(?:\s+daily)?\s+dos|"
            r"recommended dos(?:e|age)|usual adult dose)",
            blob,
            re.I,
        ):
            score += 40
        # Empagliflozin/dapagliflozin HF rows in indication tables
        if "heart failure" in blob and re.search(r"\d+(?:\.\d+)?\s*mg", blob):
            score += 30

        # Penalties for non-HF indications when multi-indication labels
        if title.startswith("2 dosage") or title == "dosage and administration":
            score -= 15
        if "pediatric" in title:
            score -= 50
        if "hypertension" in title and "heart failure" not in title and "left ventricular" not in title:
            score -= 40
        if "angina" in title:
            score -= 35
        if "prophylaxis of dvt" in title or "hip or knee" in title or "hip or knee" in blob[:80]:
            score -= 45
        if "glycemic" in title or ("diabetes" in title and "heart failure" not in title and "heart failure" not in blob):
            score -= 60
        if "other indication" in title:
            has_hf_titled = any(
                "heart failure" in (s.get("title") or "").lower()
                for s in subsections
            )
            if has_hf_titled:
                score -= 80  # prefer dedicated HF subsection
            elif "heart failure" in blob or "hhf" in blob or "cardiovascular death" in blob:
                # SGLT2i: HF dosing lives under "other indications"
                score += 100
            else:
                score -= 20
        if "cyp3a" in title or "drug interaction" in title or "dose modification" in title:
            score -= 40
        if "missed dose" in title or "temporary interruption" in title or "testing prior" in title:
            score -= 50

        # Prefer parent less when a stronger subsection exists
        if section is parent and subsections:
            score -= 10

        return (score, len(blob))

    candidates = list(subsections)
    # Also consider parent when it has usable content (hydralazine)
    if (parent.get("content") or parent.get("tables")):
        candidates.append(parent)

    if not candidates:
        return parent

    # If any HF-titled subsection exists, restrict to those first when they have content/tables
    hf_titled = [
        s for s in subsections
        if "heart failure" in (s.get("title") or "").lower()
        or "left ventricular" in (s.get("title") or "").lower()
    ]
    usable_hf = [
        s for s in hf_titled
        if len((s.get("content") or "") + _tables_as_text(s.get("tables"))) > 20
        or (s.get("tables") or [])
    ]
    pool = usable_hf if usable_hf else candidates

    ranked = sorted(pool, key=_score, reverse=True)
    best = ranked[0]
    if _score(best)[0] > 0 and len((best.get("content") or "") + _tables_as_text(best.get("tables"))) > 20:
        return best
    # HF title with empty prose but tables still preferred
    if usable_hf:
        return max(usable_hf, key=lambda s: (_score(s)[0], len(_tables_as_text(s.get("tables")))))
    contentful = [s for s in candidates if len((s.get("content") or "") + _tables_as_text(s.get("tables"))) > 50]
    if contentful:
        return max(contentful, key=lambda s: (_score(s)[0], len((s.get("content") or "") + _tables_as_text(s.get("tables")))))
    return best


def build_drug_entry(drug_data: dict) -> dict[str, Any]:
    """Build a complete drug entry from extracted data."""
    drug_name = drug_data.get("drug_name", "Unknown")
    drug_key = normalize_drug_name(drug_name)
    pipeline_id = str(drug_data.get("pipeline_id") or "").strip()
    if pipeline_id:
        aliases = _load_drug_aliases()
        if pipeline_id in aliases:
            mapped = normalize_drug_name(pipeline_id.replace("_", " "))
            drug_key = mapped if class_for_drug_key(mapped) != "Unknown" else pipeline_id
        else:
            folder_key = normalize_drug_name(pipeline_id.replace("_", " "))
            if class_for_drug_key(drug_key) == "Unknown" or "metoprolol" in pipeline_id:
                drug_key = folder_key if class_for_drug_key(folder_key) != "Unknown" else pipeline_id
    drug_class = class_for_drug_key(drug_key)

    dosage_sections = drug_data.get("dosage_information", [])
    target_section = _select_dosage_section(dosage_sections)

    renal_adjustments = extract_renal_adjustments(drug_data)
    label_egfr = drug_data.get("egfr_adjustments") or []
    if label_egfr:
        renal_adjustments = list(label_egfr) + [
            r for r in renal_adjustments
            if (r.get("egfr_min"), r.get("egfr_max"), r.get("dose"), r.get("adjustment"))
            not in {
                (x.get("egfr_min"), x.get("egfr_max"), x.get("dose"), x.get("adjustment"))
                for x in label_egfr
            }
        ]

    formulations = [{
        "formulation": "oral",
        "doses": [],
    }]

    starting_dose = None
    target_dose = None
    max_dose = None
    frequency = None
    dose_unit = None
    loading_dose = None
    route = "oral"
    table_egfr: list[dict] = []
    table_k: list[dict] = []

    def _apply_dosing(dosing: dict[str, Any], *, prefer: bool = False) -> None:
        nonlocal starting_dose, target_dose, max_dose, frequency, dose_unit, loading_dose, route
        nonlocal table_egfr, table_k
        if dosing.get("starting_dose") is not None and (starting_dose is None or prefer):
            starting_dose = dosing["starting_dose"]
            if dosing.get("dose_unit"):
                dose_unit = dosing.get("dose_unit")
            if dosing.get("route"):
                route = dosing.get("route") or route
        if dosing.get("target_dose") is not None and (target_dose is None or prefer):
            target_dose = dosing["target_dose"]
        if dosing.get("max_dose") is not None and (max_dose is None or prefer):
            max_dose = dosing["max_dose"]
        if dosing.get("frequency") and (frequency is None or prefer):
            frequency = dosing["frequency"]
        if dosing.get("dose_unit") and dose_unit is None:
            dose_unit = dosing["dose_unit"]
        if dosing.get("loading_dose") is not None and loading_dose is None:
            loading_dose = dosing["loading_dose"]
        if dosing.get("egfr_adjustments") and not table_egfr:
            table_egfr = dosing.get("egfr_adjustments") or []
        if dosing.get("potassium_adjustments") and not table_k:
            table_k = dosing.get("potassium_adjustments") or []

    candidates: list[tuple[int, dict]] = []
    if target_section:
        candidates.append((50, target_section))
    for idx, section in enumerate(dosage_sections):
        candidates.append((40 - idx, section))
        for sub in section.get("subsections") or []:
            title = (sub.get("title") or "").lower()
            score = 20
            if any(t in title for t in ("heart failure", "recommended", "adult", "usual", "dosage")):
                score += 15
            if "pediatric" in title or "preparation" in title:
                score -= 10
            if "hypertension" in title and "heart failure" not in title:
                score -= 5
            candidates.append((score, sub))

    candidates.sort(key=lambda item: item[0], reverse=True)
    seen_ids: set[int] = set()
    for score, section in candidates:
        sid = id(section)
        if sid in seen_ids:
            continue
        seen_ids.add(sid)
        dosing = extract_dosing_from_section(section)
        if dosing.get("starting_dose") is None and dosing.get("target_dose") is None:
            continue
        _apply_dosing(dosing, prefer=starting_dose is None)
        if (
            starting_dose is not None
            and target_dose is not None
            and frequency is not None
            and dose_unit is not None
        ):
            break

    if starting_dose is None and dosage_sections:
        parts: list[str] = []
        tables: list[dict] = []
        for section in dosage_sections:
            parts.append(section.get("title") or "")
            parts.append(section.get("content") or "")
            tables.extend(section.get("tables") or [])
            for sub in section.get("subsections") or []:
                parts.append(sub.get("title") or "")
                parts.append(sub.get("content") or "")
                tables.extend(sub.get("tables") or [])
        dosing = extract_dosing_from_section(
            {"title": "combined", "content": " ".join(parts), "tables": tables}
        )
        _apply_dosing(dosing, prefer=True)

    if table_egfr:
        renal_adjustments = list(table_egfr) + list(renal_adjustments)

    potassium_adjustments = list(drug_data.get("potassium_adjustments") or [])
    if table_k:
        avoids = [r for r in potassium_adjustments if r.get("adjustment") == "avoid"]
        rest = [r for r in potassium_adjustments if r.get("adjustment") != "avoid"]
        potassium_adjustments = avoids + list(table_k) + rest

    multi_factor_adjustments = list(drug_data.get("multi_factor_adjustments") or [])

    unit = dose_unit or "mg"
    formulations[0]["formulation"] = route or "oral"

    if loading_dose is not None and loading_dose != starting_dose:
        entry = {
            "label": "loading dose",
            "dose_value": loading_dose,
            "dose_unit": unit,
        }
        formulations[0]["doses"].append(entry)

    if starting_dose is not None:
        entry = {
            "label": "starting dose",
            "dose_value": starting_dose,
            "dose_unit": unit,
        }
        if frequency:
            entry["frequency"] = frequency
        formulations[0]["doses"].append(entry)

    if target_dose is not None:
        entry = {
            "label": "target dose",
            "dose_value": target_dose,
            "dose_unit": unit,
        }
        if frequency:
            entry["frequency"] = frequency
        formulations[0]["doses"].append(entry)

    if max_dose is not None and max_dose != target_dose:
        entry = {
            "label": "maximum dose",
            "dose_value": max_dose,
            "dose_unit": unit,
        }
        if frequency:
            entry["frequency"] = frequency
        formulations[0]["doses"].append(entry)

    contraindications = []
    for contra in drug_data.get("contraindications", []):
        if contra.strip():
            contraindications.append({
                "condition": "contraindication",
                "description": contra.strip()[:500],
            })

    warnings = []
    for warning in drug_data.get("warnings", []):
        if warning.get("content", "").strip():
            warnings.append({
                "type": "warning",
                "description": warning.get("content", "").strip()[:500],
            })

    return {
        "drug_key": drug_key,
        "generic_name": drug_name,
        "drug_class": drug_class,
        "formulations": formulations,
        "egfr_adjustments": renal_adjustments,
        "multi_factor_adjustments": multi_factor_adjustments,
        "potassium_adjustments": potassium_adjustments,
        "heart_rate_adjustments": drug_data.get("heart_rate_adjustments", []),
        "bp_adjustments": drug_data.get("bp_adjustments", []),
        "contraindications": contraindications,
        "warnings": warnings,
        "monitoring": drug_data.get("monitoring", []),
        "source_section": (target_section or {}).get("title"),
    }


def parse_renal_table(table_data: dict) -> list[dict[str, Any]]:
    """Parse renal adjustment table data."""
    adjustments = []
    rows = table_data.get("rows", [])

    for row in rows[1:]:  # Skip header
        if len(row) < 3:
            continue

        clearance = row[1].strip()
        dose = row[2].strip()
        joined = f"{clearance} {dose}".lower()

        # Skip pediatric / formulation rows mistaken for CrCl tables
        if "mg/kg" in joined or re.search(r"\d+\s*mg\s*/\s*\d+\s*mg", joined):
            continue
        if not re.search(r"mL/min|eGFR|CrCl|clearance|[<>≤≥=]|\d+\s*(?:to|-)\s*\d+", clearance, re.I):
            continue
        if re.search(r"\d+\s*mg", clearance, re.I) and "mL" not in clearance.lower():
            continue

        egfr_min = None
        egfr_max = None

        if ">" in clearance or "≥" in clearance:
            match = re.search(r"[>≥]\s*(\d+)", clearance)
            if match:
                egfr_min = int(match.group(1))
        elif "<" in clearance or "≤" in clearance or "<=" in clearance:
            match = re.search(r"[<≤=]\s*(\d+)", clearance)
            if match:
                egfr_max = int(match.group(1))
        elif "to" in clearance or "-" in clearance:
            match = re.search(r"(\d+)\s*(?:to|-)\s*(\d+)", clearance)
            if match:
                egfr_min = int(match.group(1))
                egfr_max = int(match.group(2))

        dose_value = None
        dose_match = re.search(r"(\d+(?:\.\d+)?)\s*mg(?!\s*/\s*kg)", dose, re.I)
        if dose_match:
            dose_value = float(dose_match.group(1))

        if dose_value is None and not any(
            t in joined for t in ("avoid", "do not", "contraindicated", "not recommended")
        ):
            continue

        if any(t in joined for t in ("avoid", "do not", "contraindicated", "not recommended")):
            adj_type = "avoid"
        elif egfr_max is not None or egfr_min is not None:
            adj_type = "reduce"
        else:
            adj_type = "none"

        if egfr_min is None and egfr_max is None:
            continue

        adjustments.append({
            "egfr_min": egfr_min,
            "egfr_max": egfr_max,
            "dose": dose_value,
            "adjustment": adj_type,
            "note": f"CrCl {clearance}: {dose}",
            "source": "fda_xml_table",
        })

    return adjustments


def extract_renal_adjustments(drug_data: dict) -> list[dict[str, Any]]:
    """Extract renal adjustments from drug data."""
    adjustments = []

    for adj in drug_data.get("renal_adjustments", []):
        for table in adj.get("tables", []):
            adjustments.extend(parse_renal_table(table))

        # Also merge text-extracted values (do not skip when tables exist)
        for val in adj.get("extracted_values", []) or []:
            egfr_max = val.get("egfr_max")
            egfr_min = val.get("egfr_min")
            dose = val.get("dose_mg")
            if egfr_min is None and egfr_max is None:
                continue
            if dose is not None and (dose <= 0 or dose > 1000):
                continue
            note_bits = []
            if egfr_min is not None:
                note_bits.append(f"min={egfr_min}")
            if egfr_max is not None:
                note_bits.append(f"max={egfr_max}")
            adjustments.append({
                "egfr_min": egfr_min,
                "egfr_max": egfr_max,
                "dose": dose,
                "adjustment": "reduce" if egfr_max is not None or (
                    egfr_min is not None and egfr_max is not None and egfr_min == egfr_max
                ) else ("reduce" if egfr_max is not None else "none"),
                "note": "Extracted from text: " + ", ".join(note_bits),
                "source": "fda_xml",
            })

    return adjustments


def convert_all_drugs(drug_labels_dir: Path, output_path: Path) -> dict[str, Any]:
    """Convert all drug label XML files to dose table JSON."""
    drugs = []

    xml_files = list(drug_labels_dir.rglob("*_label.xml"))
    print(f"Found {len(xml_files)} XML label files")

    for xml_file in xml_files:
        try:
            print(f"Processing: {xml_file.name}")
            drug_data = parse_drug_label(xml_file)
            drug_entry = build_drug_entry(drug_data)
            drugs.append(drug_entry)
            print(f"  -> {drug_entry['drug_key']}: {drug_entry.get('generic_name', 'Unknown')}")
        except Exception as e:
            print(f"Error processing {xml_file.name}: {e}")

    output = {
        "version": "2.0-derived",
        "source": "FDA XML Drug Labels",
        "description": "Dose tables extracted from FDA Structured Product Labels (SPL)",
        "drugs": drugs,
    }

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    print(f"\nConverted {len(drugs)} drugs to {output_path}")
    return output


if __name__ == "__main__":
    from pathlib import Path

    drug_labels_dir = Path("data/heart_failure/raw/drug_labels")

    if not drug_labels_dir.exists():
        print(f"Drug labels directory not found: {drug_labels_dir}")
    else:
        xml_files = list(drug_labels_dir.rglob("*_label.xml"))
        print(f"Found {len(xml_files)} XML label files\n")
        for xml_file in xml_files:
            drug_data = parse_drug_label(xml_file)
            entry = build_drug_entry(drug_data)
            print(
                f"{entry['drug_key']}: "
                f"section={entry.get('source_section')!r} "
                f"K={len(entry['potassium_adjustments'])} "
                f"HR={len(entry['heart_rate_adjustments'])} "
                f"BP={len(entry['bp_adjustments'])} "
                f"doses={len(entry['formulations'][0]['doses'])}"
            )
