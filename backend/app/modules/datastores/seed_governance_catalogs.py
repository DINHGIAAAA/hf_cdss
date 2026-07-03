"""Seed bundled governance JSON into Postgres as draft rows (first deploy)."""

from __future__ import annotations

from typing import Any


def seed_all_governance_catalogs() -> dict[str, Any]:
    from app.modules.constraint_builder.migrate_to_db import migrate_hardcoded_constraints_to_db
    from app.modules.dose_calculator.migrate_to_db import migrate_bundled_dose_rules
    from app.modules.dose_safety.migrate_to_db import migrate_bundled_dose_safety_warnings
    from app.modules.gdmt_policy.migrate_to_db import migrate_bundled_gdmt_policies
    from app.modules.interaction_checking.migrate_to_db import migrate_bundled_interaction_rules

    return {
        "constraints": migrate_hardcoded_constraints_to_db(),
        "dose_rules": migrate_bundled_dose_rules(),
        "interaction_rules": migrate_bundled_interaction_rules(),
        "gdmt_policies": migrate_bundled_gdmt_policies(),
        "dose_safety_warnings": migrate_bundled_dose_safety_warnings(),
    }


if __name__ == "__main__":
    import json

    print(json.dumps(seed_all_governance_catalogs(), indent=2))
