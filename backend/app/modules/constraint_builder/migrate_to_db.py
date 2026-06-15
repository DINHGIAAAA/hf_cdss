"""Utility to migrate existing hardcoded constraints to the database."""
import json
from pathlib import Path
from typing import Any

from app.modules.datastores.postgres import insert_or_update_constraint_definition, approve_constraint, read_approved_constraints


def migrate_hardcoded_constraints_to_db() -> dict[str, Any]:
    """Migrate constraints from constraints_v1.json to PostgreSQL database.
    
    All migrated constraints are automatically approved since they're the existing rules.
    """
    rules_path = Path(__file__).parent / "rules" / "constraints_v1.json"
    
    if not rules_path.exists():
        return {"status": "error", "message": "constraints_v1.json not found"}
    
    # Load existing constraints from database
    existing = {c["constraint_id"] for c in read_approved_constraints()}
    
    # Load hardcoded rules
    with open(rules_path, encoding="utf-8") as f:
        rules = json.load(f)
    
    inserted_count = 0
    approved_count = 0
    skipped_count = 0
    
    for rule in rules:
        constraint_id = rule["constraint_id"]
        
        # Skip if already in database
        if constraint_id in existing:
            skipped_count += 1
            continue
        
        # Insert the constraint
        success = insert_or_update_constraint_definition(rule)
        if success:
            inserted_count += 1
            # Auto-approve migrated constraints
            approve_success = approve_constraint(
                constraint_id,
                admin_user_id="system_migration",
                reason="Migrated from hardcoded constraints_v1.json"
            )
            if approve_success:
                approved_count += 1
    
    return {
        "status": "ok",
        "inserted_count": inserted_count,
        "approved_count": approved_count,
        "skipped_count": skipped_count,
        "total_processed": len(rules),
    }


if __name__ == "__main__":
    result = migrate_hardcoded_constraints_to_db()
    print(json.dumps(result, indent=2))
