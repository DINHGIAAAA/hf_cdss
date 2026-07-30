"""Seed bundled governance JSON into Postgres — deprecated; catalogs come from ingestion pipeline."""

from __future__ import annotations

from typing import Any


def _skipped(reason: str) -> dict[str, Any]:
    return {"created": 0, "skipped": 0, "status": "skipped", "reason": reason}


def seed_bundled_dose_rules() -> dict[str, Any]:
    return _skipped("Dose plans come from FDA drug-label XML via dose_calculation pipeline")


def seed_bundled_interaction_rules() -> dict[str, Any]:
    return _skipped("Interaction rules come from FDA XML + claims ingestion pipeline")


def seed_bundled_gdmt_policies() -> dict[str, Any]:
    return _skipped("GDMT policies come from guideline/claim ingestion pipeline")


def seed_bundled_dose_safety_warnings() -> dict[str, Any]:
    return _skipped("Dose safety warnings come from raw label/claims ingestion pipeline")
