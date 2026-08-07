"""Legacy migration helper — constraints now sync from the ingestion pipeline."""

from __future__ import annotations

from typing import Any


def migrate_hardcoded_constraints_to_db() -> dict[str, Any]:
    """No-op: hardcoded constraints_v1.json was removed; sync via scraper pipeline."""
    return {
        "status": "skipped",
        "reason": "Constraints are synced from artifacts/rules via sync_governance_catalog",
        "inserted_count": 0,
        "approved_count": 0,
        "skipped_count": 0,
        "total_processed": 0,
    }


if __name__ == "__main__":
    import json

    print(json.dumps(migrate_hardcoded_constraints_to_db(), indent=2))
