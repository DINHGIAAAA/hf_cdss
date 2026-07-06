"""Sync constraint rules from scraper output to PostgreSQL database."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from scraper.io.jsonl import read_jsonl

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
    from scraper.paths import data_root
    from scraper.process.drug_normalization import resolve_pipeline_drug_id
    from scraper.io.jsonl import read_jsonl as read_chunks_jsonl
    from scraper.process.evidence_linking import (
        chunk_evidence_ref,
        chunk_source_locator,
        resolve_chunk_for_rule,
    )

    drug = resolve_pipeline_drug_id(rule.get("drug")) or rule.get("drug")
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

    chunks = read_chunks_jsonl(data_root() / "artifacts/chunks/chunks.jsonl")
    linked_chunk = resolve_chunk_for_rule(rule, chunks)
    evidence_ref = chunk_evidence_ref(linked_chunk) if linked_chunk else f"rule:{rule.get('rule_id', '')}"
    source_locator = chunk_source_locator(linked_chunk) if linked_chunk else None
    claim_id = None
    for source_ref in rule.get("source_refs") or []:
        if isinstance(source_ref, dict) and source_ref.get("claim_id"):
            claim_id = source_ref.get("claim_id")
            break

    constraint_data = {
        "constraint_id": constraint_id,
        "target_drug_class": drug,
        "action": rule.get("action", "review"),
        "reason": rule.get("reason", ""),
        "risk_names": list(set(risk_names)),  # Deduplicate
        "severity_any": severity_any,
        "evidence_ref": evidence_ref,
        "clinical_sources": [
            {
                "source_id": src.get("claim_id"),
                "source_type": src.get("source_type", "unknown"),
                "title": f"{src.get('source_type')} evidence",
                "confidence": src.get("confidence", 0.8),
                "chunk_id": evidence_ref if linked_chunk else None,
                "source_locator": source_locator,
            }
            for src in rule.get("source_refs", [])
        ],
        "source": "pipeline_generated",
        "metadata": {
            "original_rule_id": rule.get("rule_id"),
            "claim_type": claim_type,
            "condition": condition,
            "chunk_id": evidence_ref if linked_chunk else None,
            "source_locator": source_locator,
            "claim_id": claim_id,
        },
    }

    # Add content hash for versioning
    constraint_data["metadata"]["content_hash"] = get_rule_content_hash(constraint_data)
    
    return constraint_data

def sync_pipeline_rules(db_functions: Any, rules_path: Path) -> dict[str, int]:
    """Convert and sync pipeline-generated rules to database, handling versioning."""
    rules = read_jsonl(rules_path)
    if any(rule.get("safety_tier") for rule in rules):
        rules = [rule for rule in rules if rule.get("safety_tier") == "usable_rules"]
    
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

def resolve_rules_path(rules_path: Path | None = None) -> Path:
    from scraper.paths import data_root

    root = data_root()
    if rules_path is not None:
        return rules_path if rules_path.is_absolute() else root / rules_path

    for candidate in (
        root / "artifacts/rules/rules_classified.jsonl",
        root / "artifacts/rules/rules.jsonl",
    ):
        if candidate.exists():
            return candidate
    return root / "artifacts/rules/rules_classified.jsonl"

def sync_constraints_to_postgres(rules_path: Path | None = None) -> dict[str, Any]:
    """Sync validated pipeline rules into PostgreSQL as draft constraint versions."""
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

    resolved_rules_path = resolve_rules_path(rules_path)
    result = {
        "status": "ok",
        "rules_path": str(resolved_rules_path),
        "synced": {},
    }

    print(f"Syncing pipeline-generated rules from {resolved_rules_path}...")
    result["synced"] = sync_pipeline_rules(db, resolved_rules_path)
    print(f"Synced: {result['synced']}")

    return result

if __name__ == "__main__":
    import sys

    from scraper.paths import project_root

    sys.path.insert(0, str(project_root()))

    parser = argparse.ArgumentParser(description="Sync classified pipeline rules into PostgreSQL.")
    parser.add_argument(
        "--rules",
        default=None,
        type=Path,
        help="Rules JSONL path relative to data/heart_failure (default: rules_classified.jsonl).",
    )
    cli_args = parser.parse_args()

    result = sync_constraints_to_postgres(cli_args.rules)
    print(json.dumps(result, indent=2))
