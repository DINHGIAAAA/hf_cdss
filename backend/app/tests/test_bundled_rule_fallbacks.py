"""Validate bundled JSON fallbacks exist and contain executable baseline rules."""

from __future__ import annotations

import json
from pathlib import Path

BUNDLED_CATALOGS = [
    {
        "path": Path("app/modules/constraint_builder/rules/constraints_v1.json"),
        "list_key": None,
        "id_key": "constraint_id",
        "min_count": 1,
    },
    {
        "path": Path("app/modules/dose_calculator/rules/hf_dose_rules_v1.json"),
        "list_key": "rules",
        "id_key": "rule_id",
        "min_count": 1,
    },
    {
        "path": Path("app/modules/interaction_checking/rules/hf_interaction_rules_v1.json"),
        "list_key": "rules",
        "id_key": "interaction_rule_id",
        "min_count": 1,
    },
    {
        "path": Path("app/modules/gdmt_policy/rules/hf_gdmt_policy_v1.json"),
        "list_key": "policies",
        "id_key": "gdmt_policy_id",
        "min_count": 4,
    },
    {
        "path": Path("app/modules/dose_safety/rules/hf_dose_safety_warnings_v1.json"),
        "list_key": "warnings",
        "id_key": "dose_safety_warning_id",
        "min_count": 4,
    },
]


def _backend_root() -> Path:
    return Path(__file__).resolve().parents[2]


def test_bundled_fallback_catalogs_are_present_and_valid() -> None:
    root = _backend_root()
    for catalog in BUNDLED_CATALOGS:
        path = root / catalog["path"]
        assert path.is_file(), f"Missing bundled fallback: {path}"
        payload = json.loads(path.read_text(encoding="utf-8"))
        items = payload if catalog["list_key"] is None else (payload.get(catalog["list_key"]) or [])
        assert len(items) >= catalog["min_count"], (
            f"{path.name} has {len(items)} items; expected >= {catalog['min_count']}"
        )
        for item in items:
            assert catalog["id_key"] in item and item[catalog["id_key"]], (
                f"{path.name} item missing {catalog['id_key']}"
            )
