"""Sync constraint rules from scraper output to PostgreSQL database.

This script:
1. Converts drug-specific rules from the pipeline output.
2. Calculates a content hash to detect changes.
3. Checks the database for the latest version of a rule.
4. If the rule has changed, it inserts a new, incremented version with 'draft' status.
5. If the rule is unchanged, it is skipped.
"""
import hashlib
import json
from pathlib import Path
from typing import Any


# Risk factor normalization mapping for claim text → constraint metadata
RISK_NAME_MAPPING = {
    "egfr": "renal_impairment",
    "renal": "renal_impairment",
    "kidney": "renal_impairment",
    "creatinine": "renal_impairment",
    "dialysis": "renal_impairment",
    "potassium": "hyperkalemia",
    "hyperkalemia": "hyperkalemia",
    "blood pressure": "hypotension",
    "hypotension": "hypotension",
    "heart rate": "bradycardia",
    "bradycardia": "bradycardia",
    "pregnancy": "pregnancy",
    "lactation": "lactation",
    "bleeding": "bleeding_risk",
    "hypersensitivity": "hypersensitivity",
    "allergy": "hypersensitivity",
    "diabetes": "hyperglycemia",
    "glycemia": "hyperglycemia",
}


def read_jsonl(path: Path) -> list[dict]:
    """Read JSONL file."""
    if not path.exists():
        return []
    with path.open(encoding="utf-8-sig") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def extract_risk_factors_from_text(text: str) -> list[str]:
    """Extract risk factor names from claim text."""
    text_lower = text.lower()
    risks = set()
    
    for keyword, risk_name in RISK_NAME_MAPPING.items():
        if keyword in text_lower:
            risks.add(risk_name)
    
    return list(risks) if risks else []


def get_rule_content_hash(constraint: dict) -> str:
    """Generate a hash for the core content of a rule to detect changes."""
    # These are the fields that define a rule's logic.
    # A change in any of these should trigger a new version.
    content_to_hash = {
        "target_drug_class": constraint.get("target_drug_class"),
        "action": constraint.get("action"),
        "reason": constraint.get("reason"),
        "risk_names": sorted(constraint.get("risk_names", [])),
        "severity_any": sorted(constraint.get("severity_any", [])),
        "evidence_ref": constraint.get("evidence_ref"),
    }
    # Use sort_keys=True to ensure consistent hash
    encoded = json.dumps(content_to_hash, sort_keys=True).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def extract_severity_from_claim(claim: dict) -> list[str]:
    """Extract severity levels from claim."""
    claim_type = claim.get("claim_type", "")
    text = claim.get("evidence", "").lower()
    
    severities = []
    
    if claim_type == "contraindication" or "contraindicated" in text:
        severities.append("high")
    elif claim_type == "renal_constraint" and "severe" in text:
        severities.append("high")
    elif claim_type in ("usage_constraint", "hyperkalemia_risk"):
        if "high" in text or "severe" in text:
            severities.append("high")
        else:
            severities.append("moderate")
    
    return severities if severities else ["moderate"]


def convert_rule_to_constraint(rule: dict) -> dict[str, Any]:
    """Convert a generated rule to constraint_rules table format."""
    drug = rule.get("drug")
    claim_type = rule.get("claim_type", "")
    condition = rule.get("condition", {})
    
    # Extract risk factors from condition
    risk_names = []
    severity_any = []
    
    if condition.get("egfr"):
        risk_names.append("renal_impairment")
        severity_any.extend(["high", "moderate"])
    
    if condition.get("potassium"):
        risk_names.append("hyperkalemia")
        severity_any.append("high")
    
    if condition.get("indication"):
        # Add indication-specific risks
        pass
    
    if not risk_names:
        # Try to infer from claim type and rule
        for source_ref in rule.get("source_refs", []):
            evidence = source_ref.get("evidence", "")
            evidence_risks = extract_risk_factors_from_text(evidence)
            risk_names.extend(evidence_risks)
        risk_names = list(set(risk_names))
    
    if not severity_any:
        severity_any = extract_severity_from_claim({
            "claim_type": claim_type,
            "evidence": rule.get("reason", "")
        })
    
    # Generate constraint ID
    constraint_id = rule.get("rule_id", f"{drug}_{claim_type}_{rule.get('action', 'unknown')}")
    
    constraint_data = {
        "constraint_id": constraint_id,
        "target_drug_class": drug,
        "action": rule.get("action", "review"),
        "reason": rule.get("reason", ""),
        "risk_names": list(set(risk_names)),  # Deduplicate
        "severity_any": severity_any,
        "evidence_ref": f"rule:{rule.get('rule_id', '')}",
        "clinical_sources": [
            {
                "source_id": src.get("claim_id"),
                "source_type": src.get("source_type", "unknown"),
                "title": f"{src.get('source_type')} evidence",
                "confidence": src.get("confidence", 0.8),
            }
            for src in rule.get("source_refs", [])
        ],
        "source": "pipeline_generated",
        "metadata": {
            "original_rule_id": rule.get("rule_id"),
            "claim_type": claim_type,
            "condition": condition,
        },
    }

    # Add content hash for versioning
    constraint_data["metadata"]["content_hash"] = get_rule_content_hash(constraint_data)
    
    return constraint_data


def sync_pipeline_rules(db_functions: Any, rules_path: Path) -> dict[str, int]:
    """Convert and sync pipeline-generated rules to database, handling versioning."""
    rules = read_jsonl(rules_path)
    
    new_versions_created = 0
    skipped_unchanged = 0
    errors = 0
    
    for rule in rules:
        try:
            drug = rule.get("drug")
            
            if not drug:
                continue
            
            # Convert rule to constraint format
            new_constraint = convert_rule_to_constraint(rule)
            constraint_id = new_constraint["constraint_id"]
            new_hash = new_constraint["metadata"]["content_hash"]

            # Check for existing version
            latest_version = db_functions.get_latest_constraint_rule_version(constraint_id)
            
            if latest_version:
                # Rule exists, check for changes
                latest_hash = latest_version.get("metadata", {}).get("content_hash")
                if latest_hash == new_hash:
                    # No change in content, skip
                    skipped_unchanged += 1
                    continue
                
                # Content has changed, increment version
                new_constraint["version"] = latest_version["version"] + 1
            else:
                # First time seeing this rule
                new_constraint["version"] = 1
            
            # Insert with draft status (admin must review)
            if db_functions.insert_constraint_rule(new_constraint):
                new_versions_created += 1
            else:
                errors += 1
        except Exception as e:
            print(f"Error converting rule {rule.get('rule_id')}: {e}")
            errors += 1
    
    return {"new_versions_created": new_versions_created, "skipped_unchanged": skipped_unchanged, "errors": errors}


def sync_constraints_to_postgres() -> dict[str, Any]:
    """Main sync function - call from backend initialization."""
    # Import here to avoid circular dependencies
    from app.modules.datastores.postgres import (
        insert_constraint_rule,
        get_latest_constraint_rule_version,
    )
    
    # Create a simple db_functions object
    class DbFunctions:
        @staticmethod
        def insert_constraint_rule(rule):
            return insert_constraint_rule(rule)
        
        @staticmethod
        def get_latest_constraint_rule_version(constraint_id):
            return get_latest_constraint_rule_version(constraint_id)
    
    db = DbFunctions()
    
    # Paths (adjust as needed for your setup)
    rules_path = Path(__file__).parent.parent.parent / "data" / "heart_failure" / "artifacts" / "rules" / "rules.jsonl"
    
    result = {
        "status": "ok",
        "synced": {},
    }
    
    # Sync pipeline rules
    print("Syncing pipeline-generated rules...")
    result["synced"] = sync_pipeline_rules(db, rules_path)
    print(f"Synced: {result['synced']}")
    
    return result


if __name__ == "__main__":
    import sys
    sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))
    
    result = sync_constraints_to_postgres()
    print(json.dumps(result, indent=2))
