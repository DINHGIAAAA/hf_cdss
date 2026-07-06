"""JSON Schema and governance validation for dose rule bundles."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.modules.dose_calculator.dose_rules_paths import resolve_dose_rules_bundle_path
from app.modules.dose_calculator.rule_loader import load_executable_dose_rules, load_dose_rules_bundle
from app.modules.dose_calculator.rule_validation import (
    DoseRulesValidationError,
    validate_all_bundled_versions,
    validate_bundle_file,
)


def test_v1_bundle_passes_json_schema() -> None:
    result = validate_bundle_file(resolve_dose_rules_bundle_path(), strict=True)
    assert result["version"] == "hf_dose_rules_v1"
    assert len(result["rules"]) >= 17


def test_all_bundled_versions_validate_in_ci() -> None:
    bundles = validate_all_bundled_versions()
    versions = {item["version"] for item in bundles}
    assert "hf_dose_rules_v1" in versions


def test_runtime_loader_validates_executable_rules() -> None:
    rules = load_executable_dose_rules()
    assert rules
    for rule in rules:
        assert rule.get("rule_id")
        assert rule.get("calculation_type")


def test_invalid_rule_rejected_in_strict_mode(tmp_path: Path) -> None:
    bundle = {
        "version": "hf_dose_rules_v99",
        "rules": [
            {
                "rule_id": "bad_rule",
                "drug_keys": [],
                "calculation_type": "unknown_type",
            }
        ],
    }
    path = tmp_path / "hf_dose_rules_v99.json"
    path.write_text(json.dumps(bundle), encoding="utf-8")
    with pytest.raises(DoseRulesValidationError):
        validate_bundle_file(path, strict=True)


def test_load_bundle_reports_source() -> None:
    bundle = load_dose_rules_bundle()
    assert bundle.get("version")
    assert bundle.get("source")
