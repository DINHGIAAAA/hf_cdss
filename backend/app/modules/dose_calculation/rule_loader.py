"""Load dose tables — Postgres approved dose_rules first, FDA XML fallback for local dev."""

from __future__ import annotations

import logging
import os
from functools import lru_cache
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Path to FDA XML drug labels (dev fallback only; production uses Postgres dose_rules).
DRUG_LABELS_DIR = Path(
    os.environ.get(
        "HF_CDSS_RAW_ROOT",
        str(Path(__file__).resolve().parents[4] / ".work" / "heart_failure" / "raw"),
    )
) / "drug_labels"


def _load_from_xml() -> dict[str, Any]:
    """Load dose tables directly from FDA XML drug labels (local dev fallback)."""
    from app.modules.dose_calculation.convert_extracted_doses import build_drug_entry
    from app.modules.dose_calculation.xml_dose_extractor import parse_drug_label

    drugs = []

    if not DRUG_LABELS_DIR.exists():
        logger.debug("FDA XML drug labels not present at %s (dev fallback skipped)", DRUG_LABELS_DIR)
        return {
            "version": "2.0-derived-empty",
            "source": "fda_xml_labels_unavailable",
            "source_path": str(DRUG_LABELS_DIR),
            "drugs": [],
        }

    xml_files = list(DRUG_LABELS_DIR.rglob("*_label.xml"))

    for xml_file in xml_files:
        try:
            drug_data = parse_drug_label(xml_file)
            drug_entry = build_drug_entry(drug_data)
            drugs.append(drug_entry)
        except Exception as exc:
            logger.warning("Error processing dose label %s: %s", xml_file.name, exc)

    return {
        "version": "2.0-derived",
        "source": "fda_xml_labels",
        "source_path": str(DRUG_LABELS_DIR),
        "drugs": drugs,
    }


def _merge_drug_catalogs(primary: dict[str, Any], secondary: dict[str, Any]) -> dict[str, Any]:
    """Keep Postgres entries; add XML drugs only for keys not already governed."""
    by_key = {str(d.get("drug_key")): d for d in primary.get("drugs") or [] if d.get("drug_key")}
    for drug in secondary.get("drugs") or []:
        key = drug.get("drug_key")
        if key and key not in by_key:
            by_key[key] = drug
    return {
        "version": primary.get("version") or secondary.get("version"),
        "source": primary.get("source") or secondary.get("source"),
        "drugs": list(by_key.values()),
    }


@lru_cache(maxsize=1)
def load_dose_tables() -> dict[str, Any]:
    from app.modules.dose_calculation.postgres_dose_loader import load_tables_from_postgres

    postgres_tables = load_tables_from_postgres()
    if postgres_tables.get("drugs"):
        xml_tables = _load_from_xml()
        if xml_tables.get("drugs"):
            return _merge_drug_catalogs(postgres_tables, xml_tables)
        return postgres_tables

    xml_tables = _load_from_xml()
    if xml_tables.get("drugs"):
        logger.info(
            "No approved Postgres dose_rules loaded; using FDA XML fallback (%s drugs)",
            len(xml_tables.get("drugs") or []),
        )
        return xml_tables

    logger.warning(
        "Dose catalog empty: approve dose_rules in governance or provide FDA XML under %s",
        DRUG_LABELS_DIR,
    )
    return {
        "version": postgres_tables.get("version") or xml_tables.get("version"),
        "source": postgres_tables.get("source") or xml_tables.get("source"),
        "drugs": [],
    }


def invalidate_dose_tables_cache() -> None:
    from app.modules.dose_calculation.postgres_dose_loader import invalidate_postgres_dose_rules_cache

    load_dose_tables.cache_clear()
    invalidate_postgres_dose_rules_cache()


def get_drug_by_key(drug_key: str) -> dict[str, Any] | None:
    """Get drug configuration by drug key."""
    tables = load_dose_tables()
    needle = drug_key.lower()
    for drug in tables.get("drugs", []):
        if drug.get("drug_key") == needle:
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
