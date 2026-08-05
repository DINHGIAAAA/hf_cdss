"""Dose Calculation Module.

Builds HF medication dose plans from approved Postgres ``dose_rules`` (primary),
with optional FDA XML label fallback for local development.
"""

from app.modules.dose_calculation.service import (
    build_dose_plans,
    calculate_multiple_doses,
    calculate_single_dose,
    dose_source_version,
    get_available_drugs,
    get_drug_info,
    invalidate_dose_label_cache,
)

__all__ = [
    "build_dose_plans",
    "calculate_single_dose",
    "calculate_multiple_doses",
    "dose_source_version",
    "get_available_drugs",
    "get_drug_info",
    "invalidate_dose_label_cache",
]
