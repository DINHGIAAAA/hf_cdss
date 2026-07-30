"""Verify production bundled rule JSON files were removed."""

from __future__ import annotations

from pathlib import Path

import pytest


def _backend_root() -> Path:
    return Path(__file__).resolve().parents[2]


def test_bundled_production_rule_files_are_removed() -> None:
    root = _backend_root()
    removed = [
        root / "app/modules/constraint_builder/rules/constraints_v1.json",
        root / "app/modules/interaction_checking/rules/hf_interaction_rules_v1.json",
        root / "app/modules/gdmt_policy/rules/hf_gdmt_policy_v1.json",
        root / "app/modules/dose_safety/rules/hf_dose_safety_warnings_v1.json",
    ]
    for path in removed:
        assert not path.is_file(), f"Bundled production rule file still present: {path}"


def test_fda_label_dose_source_is_available() -> None:
    from app.modules.dose_calculation import dose_source_version, get_available_drugs
    from app.modules.dose_calculation.rule_loader import DRUG_LABELS_DIR

    assert dose_source_version() == "fda_xml_labels"
    if not DRUG_LABELS_DIR.is_dir():
        pytest.skip(f"Drug labels not present locally: {DRUG_LABELS_DIR}")
    drugs = get_available_drugs()
    assert len(drugs) >= 1
    assert any(d.get("drug_key") == "eplerenone" for d in drugs)
