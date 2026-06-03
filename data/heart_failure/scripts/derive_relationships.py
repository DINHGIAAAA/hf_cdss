import argparse
import hashlib
import json
import re
from pathlib import Path


def read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8-sig") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def write_jsonl(records: list[dict], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")


def slug(value: str) -> str:
    value = re.sub(r"[^a-zA-Z0-9]+", "_", value or "").strip("_").lower()
    return value or "unknown"


def relationship_id(source_id: str, rel_type: str, target_id: str) -> str:
    raw = f"{source_id}|{rel_type}|{target_id}"
    return "rel_" + hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


def relationship(source_id: str, source_type: str, rel_type: str, target_id: str, target_type: str, metadata: dict) -> dict:
    return {
        "relationship_id": relationship_id(source_id, rel_type, target_id),
        "source_id": source_id,
        "source_type": source_type,
        "relationship_type": rel_type,
        "target_id": target_id,
        "target_type": target_type,
        "metadata": metadata,
    }


def drug_id(drug: str) -> str:
    return f"drug:{slug(drug)}"


def claim_id(claim: dict) -> str:
    return f"claim:{claim['claim_id']}"


def rule_id(rule: dict) -> str:
    return f"rule:{rule['rule_id']}"


def condition_from_claim(claim: dict) -> str:
    evidence = claim.get("evidence") or claim.get("claim") or ""
    evidence = re.sub(r"\s+", " ", evidence).strip()
    for pattern in (
        r"contraindicated in patients? with (.+?)(?:\.|$)",
        r"contraindicated in (.+?)(?:\.|$)",
        r"contraindicated for (.+?)(?:\.|$)",
    ):
        match = re.search(pattern, evidence, flags=re.IGNORECASE)
        if match:
            return match.group(1).strip(" :;")
    return evidence[:160]


def risk_from_claim(claim: dict) -> str:
    evidence = claim.get("evidence") or claim.get("claim") or ""
    for term in ("hyperkalemia", "bleeding", "hypotension", "hypoglycemia", "renal impairment"):
        if term in evidence.lower():
            return term
    return evidence[:160]


def labs_from_text(text: str) -> list[str]:
    labs = []
    haystack = text.lower()
    for lab in ("egfr", "serum potassium", "potassium", "creatinine", "blood pressure", "hba1c", "urine glucose"):
        if lab in haystack:
            labs.append(lab)
    return labs


def relationships_from_claims(claims: list[dict]) -> list[dict]:
    rels = []
    for claim in claims:
        drug = claim.get("drug")
        if not drug:
            continue

        source = drug_id(drug)
        claim_target = claim_id(claim)
        base_metadata = {
            "claim_id": claim.get("claim_id"),
            "claim_type": claim.get("claim_type"),
            "source_section": claim.get("source_section"),
            "confidence": claim.get("confidence"),
        }

        rels.append(relationship(source, "Drug", "HAS_CLAIM", claim_target, "Claim", base_metadata))

        claim_type = claim.get("claim_type")
        if claim_type == "contraindication":
            condition = condition_from_claim(claim)
            rels.append(
                relationship(
                    source,
                    "Drug",
                    "HAS_CONTRAINDICATION",
                    f"condition:{slug(condition)}",
                    "Condition",
                    {**base_metadata, "condition": condition},
                )
            )
        elif claim_type in {"adverse_reaction", "hyperkalemia_risk", "renal_constraint", "usage_constraint"}:
            risk = risk_from_claim(claim)
            rels.append(
                relationship(
                    source,
                    "Drug",
                    "HAS_WARNING",
                    f"risk:{slug(risk)}",
                    "Risk",
                    {**base_metadata, "risk": risk},
                )
            )

        if "monitor" in (claim.get("claim") or "").lower() or "monitor" in claim_type:
            for lab in labs_from_text(claim.get("claim") or ""):
                rels.append(
                    relationship(
                        source,
                        "Drug",
                        "REQUIRES_MONITORING",
                        f"lab:{slug(lab)}",
                        "Lab",
                        {**base_metadata, "lab": lab},
                    )
                )

    return rels


def relationships_from_rules(rules: list[dict]) -> list[dict]:
    rels = []
    for rule in rules:
        drug = rule.get("drug")
        if not drug:
            continue
        source = drug_id(drug)
        target = rule_id(rule)
        rels.append(
            relationship(
                source,
                "Drug",
                "HAS_RULE",
                target,
                "Rule",
                {
                    "rule_id": rule.get("rule_id"),
                    "action": rule.get("action"),
                    "claim_type": rule.get("claim_type"),
                    "condition": rule.get("condition"),
                },
            )
        )
        for ref in rule.get("source_refs", []):
            if ref.get("claim_id"):
                rels.append(
                    relationship(
                        f"claim:{ref['claim_id']}",
                        "Claim",
                        "SUPPORTS_RULE",
                        target,
                        "Rule",
                        {"rule_id": rule.get("rule_id"), "confidence": ref.get("confidence")},
                    )
                )
    return rels


def main() -> None:
    parser = argparse.ArgumentParser(description="Derive placeholder graph relationships from dataset claims and rules.")
    parser.add_argument("--claims", default="artifacts/claims/claims.jsonl", type=Path)
    parser.add_argument("--rules", default="artifacts/rules/rules.jsonl", type=Path)
    parser.add_argument("--output", default="artifacts/relationships/relationships.jsonl", type=Path)
    args = parser.parse_args()

    relationships = relationships_from_claims(read_jsonl(args.claims))
    relationships.extend(relationships_from_rules(read_jsonl(args.rules)))

    unique = {}
    for rel in relationships:
        unique[rel["relationship_id"]] = rel

    write_jsonl(list(unique.values()), args.output)
    print(f"Wrote {len(unique)} relationships to {args.output}")


if __name__ == "__main__":
    main()
