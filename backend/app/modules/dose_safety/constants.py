"""Dose safety ceiling and floor constants for HF medications.

These constants define maximum (ceiling) and minimum (floor) doses for safety checks.
Values are based on AHA/ACC/HFSA 2022 guidelines and FDA labeling.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class DoseLimit:
    value: float
    unit: str
    frequency: str


# Beta-blockers
DOSE_CEILING_BETA_BLOCKER: dict[str, DoseLimit] = {
    "bisoprolol": DoseLimit(value=10, unit="mg", frequency="once daily"),
    "carvedilol": DoseLimit(value=25, unit="mg", frequency="twice daily"),
    "metoprolol_succinate": DoseLimit(value=200, unit="mg", frequency="once daily"),
    "carvedilol_high_weight": DoseLimit(value=50, unit="mg", frequency="twice daily"),
}

# ACE Inhibitors
DOSE_CEILING_ACEI: dict[str, DoseLimit] = {
    "enalapril": DoseLimit(value=10, unit="mg", frequency="twice daily"),
    "lisinopril": DoseLimit(value=20, unit="mg", frequency="once daily"),
    "ramipril": DoseLimit(value=10, unit="mg", frequency="once daily"),
    "captopril": DoseLimit(value=50, unit="mg", frequency="three times daily"),
}

# ARNI
DOSE_CEILING_ARNI: dict[str, DoseLimit] = {
    "sacubitril_valsartan": DoseLimit(value=97, unit="mg", frequency="twice daily"),
}

# MRA (Mineralocorticoid Receptor Antagonists)
DOSE_CEILING_MRA: dict[str, DoseLimit] = {
    "spironolactone": DoseLimit(value=50, unit="mg", frequency="once daily"),
    "eplerenone": DoseLimit(value=50, unit="mg", frequency="once daily"),
}

# SGLT2 Inhibitors
DOSE_CEILING_SGLT2I: dict[str, DoseLimit] = {
    "dapagliflozin": DoseLimit(value=10, unit="mg", frequency="once daily"),
    "empagliflozin": DoseLimit(value=10, unit="mg", frequency="once daily"),
    "empagliflozin_hf": DoseLimit(value=25, unit="mg", frequency="once daily"),
}

# Loop Diuretics
DOSE_CEILING_LOOP_DIURETIC: dict[str, DoseLimit] = {
    "furosemide": DoseLimit(value=160, unit="mg", frequency="once daily"),
    "bumetanide": DoseLimit(value=10, unit="mg", frequency="once daily"),
    "torsemide": DoseLimit(value=40, unit="mg", frequency="once daily"),
}

# IV Loop Diuretics (for acute decompensated HF)
DOSE_CEILING_IV_LOOP_DIURETIC: dict[str, DoseLimit] = {
    "furosemide_iv": DoseLimit(value=200, unit="mg", frequency="once daily"),
    "bumetanide_iv": DoseLimit(value=10, unit="mg", frequency="once daily"),
    "torsemide_iv": DoseLimit(value=40, unit="mg", frequency="once daily"),
}

# Floor (minimum effective dose) - doses below this are unlikely therapeutic
DOSE_FLOOR_BETA_BLOCKER: dict[str, DoseLimit] = {
    "bisoprolol": DoseLimit(value=2.5, unit="mg", frequency="once daily"),
    "carvedilol": DoseLimit(value=3.125, unit="mg", frequency="twice daily"),
    "metoprolol_succinate": DoseLimit(value=12.5, unit="mg", frequency="once daily"),
}

DOSE_FLOOR_ACEI: dict[str, DoseLimit] = {
    "enalapril": DoseLimit(value=2.5, unit="mg", frequency="twice daily"),
    "lisinopril": DoseLimit(value=2.5, unit="mg", frequency="once daily"),
    "ramipril": DoseLimit(value=1.25, unit="mg", frequency="once daily"),
}

DOSE_FLOOR_ARNI: DoseLimit(value=24, unit="mg", frequency="twice daily")

DOSE_FLOOR_MRA: DoseLimit(value=12.5, unit="mg", frequency="once daily")

DOSE_FLOOR_SGLT2I: DoseLimit(value=5, unit="mg", frequency="once daily")

DOSE_FLOOR_LOOP_DIURETIC: dict[str, DoseLimit] = {
    "furosemide": DoseLimit(value=20, unit="mg", frequency="once daily"),
    "bumetanide": DoseLimit(value=0.5, unit="mg", frequency="once daily"),
    "torsemide": DoseLimit(value=10, unit="mg", frequency="once daily"),
}


def get_dose_ceiling(drug_class: str, drug_name: str | None = None) -> DoseLimit | None:
    """Get ceiling dose for a drug class or specific drug."""
    if drug_class == "beta_blocker" and drug_name:
        return DOSE_CEILING_BETA_BLOCKER.get(drug_name.lower().replace(" ", "_"))
    if drug_class == "acei" or drug_class == "ace_inhibitor":
        return DOSE_CEILING_ACEI.get(drug_name.lower().replace(" ", "_")) if drug_name else None
    if drug_class == "arni":
        return DOSE_CEILING_ARNI.get(drug_name.lower().replace(" ", "_")) if drug_name else None
    if drug_class == "mra":
        return DOSE_CEILING_MRA.get(drug_name.lower().replace(" ", "_")) if drug_name else None
    if drug_class == "sglt2i" or drug_class == "sglt2_inhibitor":
        return DOSE_CEILING_SGLT2I.get(drug_name.lower().replace(" ", "_")) if drug_name else None
    if drug_class == "loop_diuretic":
        return DOSE_CEILING_LOOP_DIURETIC.get(drug_name.lower().replace(" ", "_")) if drug_name else None
    return None


def get_dose_floor(drug_class: str, drug_name: str | None = None) -> DoseLimit | None:
    """Get floor dose for a drug class or specific drug."""
    if drug_class == "beta_blocker" and drug_name:
        return DOSE_FLOOR_BETA_BLOCKER.get(drug_name.lower().replace(" ", "_"))
    if drug_class == "acei" or drug_class == "ace_inhibitor":
        return DOSE_FLOOR_ACEI.get(drug_name.lower().replace(" ", "_")) if drug_name else None
    if drug_class == "arni":
        return DOSE_FLOOR_ARNI
    if drug_class == "mra":
        return DOSE_FLOOR_MRA
    if drug_class == "sglt2i" or drug_class == "sglt2_inhibitor":
        return DOSE_FLOOR_SGLT2I
    if drug_class == "loop_diuretic":
        return DOSE_FLOOR_LOOP_DIURETIC.get(drug_name.lower().replace(" ", "_")) if drug_name else None
    return None


def is_dose_above_ceiling(current_dose: float, drug_class: str, drug_name: str | None = None) -> bool:
    """Check if current dose exceeds safety ceiling."""
    ceiling = get_dose_ceiling(drug_class, drug_name)
    if ceiling is None:
        return False
    return current_dose > ceiling.value


def is_dose_below_floor(current_dose: float, drug_class: str, drug_name: str | None = None) -> bool:
    """Check if current dose is below therapeutic floor."""
    floor = get_dose_floor(drug_class, drug_name)
    if floor is None:
        return False
    return current_dose < floor.value
