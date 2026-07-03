"""JSON Schema validation for dose rule bundles and runtime readiness checks."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

from app.core.config import settings
from app.modules.dose_calculator.bundle_paths import expected_bundle_version_label, resolve_dose_rules_bundle_path


_SCHEMA_PATH = Path(__file__).resolve().parent / "schemas" / "hf_dose_rules_bundle.schema.json"

SUPPORTED_CALCULATION_TYPES = frozenset(
    {
        "fixed_titration",
        "weight_adjusted_target",
        "crcl_bracket",
        "dual_criteria_reduction",
        "criteria_reduction",
        "crcl_threshold_dose",
        "dabigatran_dose",
        "congestion_range",
        "fixed_dose",
        "step_titration",
        "warfarin_inr",
    }
)


class DoseRulesValidationError(ValueError):
    def __init__(self, message: str, *, errors: list[str] | None = None) -> None:
        super().__init__(message)
        self.errors = list(errors or [])


@lru_cache(maxsize=1)
def _bundle_validator() -> Draft202012Validator:
    schema = json.loads(_SCHEMA_PATH.read_text(encoding="utf-8"))
    return Draft202012Validator(schema)


def _format_validation_errors(errors: list[Any], *, prefix: str = "") -> list[str]:
    formatted: list[str] = []
    for error in errors:
        path = ".".join(str(part) for part in error.absolute_path) or "<root>"
        formatted.append(f"{prefix}{path}: {error.message}")
    return formatted


def validate_rule_dict(rule: dict[str, Any], *, rule_index: int | None = None) -> list[str]:
    prefix = f"rules[{rule_index}]" if rule_index is not None else "rules[0]"
    wrapper = {"version": "hf_dose_rules_v1", "rules": [rule]}
    validator = _bundle_validator()
    formatted: list[str] = []
    for error in validator.iter_errors(wrapper):
        path = list(error.absolute_path)
        if len(path) < 2 or path[0] != "rules" or path[1] != 0:
            continue
        subpath = ".".join(str(part) for part in path[2:]) or "<root>"
        formatted.append(f"{prefix}.{subpath}: {error.message}")
    return formatted


def assert_unique_rule_ids(rules: list[dict[str, Any]]) -> None:
    seen: set[str] = set()
    duplicates: list[str] = []
    for rule in rules:
        rule_id = str(rule.get("rule_id") or "").strip()
        if not rule_id:
            continue
        if rule_id in seen:
            duplicates.append(rule_id)
        seen.add(rule_id)
    if duplicates:
        raise DoseRulesValidationError(
            "Duplicate rule_id values in dose rules bundle",
            errors=[f"duplicate rule_id: {rule_id}" for rule_id in sorted(set(duplicates))],
        )


def validate_bundle_payload(
    payload: dict[str, Any],
    *,
    strict: bool | None = None,
    expected_version: str | None = None,
    source_label: str = "bundle",
) -> dict[str, Any]:
    if strict is None:
        strict = bool(getattr(settings, "dose_rules_validation_strict", True))

    validator = _bundle_validator()
    schema_errors = _format_validation_errors(list(validator.iter_errors(payload)))
    if schema_errors:
        raise DoseRulesValidationError(
            f"Invalid dose rules {source_label}",
            errors=schema_errors,
        )

    rules = list(payload.get("rules") or [])
    assert_unique_rule_ids(rules)

    if expected_version and payload.get("version") != expected_version:
        message = (
            f"Dose rules {source_label} version mismatch: "
            f"expected {expected_version}, got {payload.get('version')!r}"
        )
        if strict:
            raise DoseRulesValidationError(message)
        schema_errors.append(message)

    invalid_rules: list[str] = []
    valid_rules: list[dict[str, Any]] = []
    for index, rule in enumerate(rules):
        rule_errors = validate_rule_dict(rule, rule_index=index)
        calc_type = rule.get("calculation_type")
        if calc_type not in SUPPORTED_CALCULATION_TYPES:
            rule_errors.append(f"rules[{index}] calculation_type: unsupported calculator {calc_type!r}")
        if rule_errors:
            invalid_rules.extend(rule_errors)
            if not strict:
                continue
        valid_rules.append(rule)

    if invalid_rules and strict:
        raise DoseRulesValidationError(f"Invalid dose rules in {source_label}", errors=invalid_rules)

    normalized = dict(payload)
    normalized["rules"] = valid_rules if not strict else rules
    if invalid_rules and not strict:
        normalized["_validation_warnings"] = invalid_rules
    return normalized


def validate_bundle_file(path: Path, *, strict: bool | None = None) -> dict[str, Any]:
    if not path.is_file():
        raise DoseRulesValidationError(f"Dose rules bundle not found: {path}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    return validate_bundle_payload(payload, strict=strict, source_label=str(path))


def validate_runtime_bundle(bundle: dict[str, Any], *, strict: bool | None = None) -> dict[str, Any]:
    """Validate executable rules in a runtime bundle (Postgres or JSON fallback)."""
    if strict is None:
        strict = bool(getattr(settings, "dose_rules_validation_strict", True))

    rules = list(bundle.get("rules") or [])
    assert_unique_rule_ids(rules)

    invalid_rules: list[str] = []
    valid_rules: list[dict[str, Any]] = []
    for index, rule in enumerate(rules):
        rule_errors = validate_rule_dict(rule, rule_index=index)
        calc_type = rule.get("calculation_type")
        if calc_type not in SUPPORTED_CALCULATION_TYPES:
            rule_errors.append(f"rules[{index}] calculation_type: unsupported calculator {calc_type!r}")
        if rule_errors:
            invalid_rules.extend(rule_errors)
            if not strict:
                continue
        valid_rules.append(rule)

    if invalid_rules and strict:
        raise DoseRulesValidationError("Invalid dose rules at runtime", errors=invalid_rules)

    normalized = dict(bundle)
    normalized["rules"] = valid_rules if invalid_rules and not strict else rules
    if invalid_rules and not strict:
        normalized["_validation_warnings"] = invalid_rules
    return normalized


def check_runtime_dose_rules() -> dict[str, Any]:
    """Load and validate the active dose-rules bundle for readiness probes."""
    from app.modules.dose_calculator.rule_loader import load_dose_rules_bundle

    bundle = load_dose_rules_bundle()
    validated = validate_runtime_bundle(bundle)
    rules = list(validated.get("rules") or [])
    if not rules:
        raise DoseRulesValidationError("No executable dose rules available")

    warnings = list(validated.get("_validation_warnings") or [])
    result: dict[str, Any] = {
        "status": "ok",
        "version": str(bundle.get("version") or "unknown"),
        "source": str(bundle.get("source") or "unknown"),
        "rule_count": len(rules),
        "active_bundle_version": expected_bundle_version_label(),
        "bundle_path": str(resolve_dose_rules_bundle_path()),
    }
    if warnings:
        result["validation_warnings"] = warnings
    return result


def validate_all_bundled_versions(*, rules_dir: Path | None = None) -> list[dict[str, Any]]:
    """CI helper: validate every hf_dose_rules_v*.json in the rules directory."""
    directory = rules_dir or resolve_dose_rules_bundle_path().parent
    results: list[dict[str, Any]] = []
    for path in sorted(directory.glob("hf_dose_rules_v*.json")):
        validated = validate_bundle_file(path, strict=True)
        results.append(
            {
                "path": str(path),
                "version": validated.get("version"),
                "rule_count": len(validated.get("rules") or []),
            }
        )
    if not results:
        raise DoseRulesValidationError(f"No dose rule bundles found in {directory}")
    return results
