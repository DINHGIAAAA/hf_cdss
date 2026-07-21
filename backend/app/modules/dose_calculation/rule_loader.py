"""Load dose tables - derived directly from FDA XML drug labels."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any


# Path to FDA XML drug labels
DRUG_LABELS_DIR = Path("data/heart_failure/raw/drug_labels")


def _load_from_xml() -> dict[str, Any]:
    """Load dose tables directly from FDA XML drug labels."""
    from app.modules.dose_calculation.xml_dose_extractor import parse_drug_label
    from app.modules.dose_calculation.convert_extracted_doses import build_drug_entry

    drugs = []

    # Find all XML files
    if not DRUG_LABELS_DIR.exists():
        raise FileNotFoundError(f"Drug labels directory not found: {DRUG_LABELS_DIR}")

    xml_files = list(DRUG_LABELS_DIR.rglob("*_label.xml"))

    for xml_file in xml_files:
        try:
            drug_data = parse_drug_label(xml_file)
            drug_entry = build_drug_entry(drug_data)
            drugs.append(drug_entry)
        except Exception as e:
            print(f"Error processing {xml_file.name}: {e}")

    return {
        "version": "2.0-derived",
        "source": "FDA XML Drug Labels",
        "source_path": str(DRUG_LABELS_DIR),
        "drugs": drugs,
    }


@lru_cache(maxsize=1)
def load_dose_tables() -> dict[str, Any]:
    """Load dose tables - directly from FDA XML."""
    return _load_from_xml()


def get_drug_by_key(drug_key: str) -> dict[str, Any] | None:
    """Get drug configuration by drug key."""
    tables = load_dose_tables()
    for drug in tables.get("drugs", []):
        if drug.get("drug_key") == drug_key.lower():
            return drug
    return None


def list_available_drugs() -> list[dict[str, Any]]:
    """List all drugs in the dose tables."""
    tables = load_dose_tables()
    return [
        {
            "drug_key": d.get("drug_key"),
            "generic_name": d.get("generic_name"),
            "drug_class": d.get("drug_class"),
        }
        for d in tables.get("drugs", [])
    ]
