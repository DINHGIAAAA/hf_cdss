"""Seed bundled governance JSON into Postgres as draft rows (first deploy)."""

from __future__ import annotations

from typing import Any

from app.modules.constraint_builder.migrate_to_db import migrate_hardcoded_constraints_to_db
from app.modules.datastores.bundled_catalog_seed import (
    seed_bundled_dose_rules,
    seed_bundled_dose_safety_warnings,
    seed_bundled_gdmt_policies,
    seed_bundled_interaction_rules,
)


def seed_all_governance_catalogs() -> dict[str, Any]:
    return {
        "constraints": migrate_hardcoded_constraints_to_db(),
        "dose_rules": seed_bundled_dose_rules(),
        "interaction_rules": seed_bundled_interaction_rules(),
        "gdmt_policies": seed_bundled_gdmt_policies(),
        "dose_safety_warnings": seed_bundled_dose_safety_warnings(),
    }


if __name__ == "__main__":
    import json

    print(json.dumps(seed_all_governance_catalogs(), indent=2))
