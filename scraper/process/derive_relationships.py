import argparse
import hashlib
import json
import re
from pathlib import Path

from scraper.io.jsonl import read_jsonl, write_jsonl
from scraper.kg.identifiers import chunk_node_id, document_node_id, section_id_for_record, section_node_id, slug
from scraper.process.evidence_linking import find_chunk_for_claim


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


def relationships_from_chunk_grounding(claims: list[dict], chunks: list[dict]) -> list[dict]:
    rels: list[dict] = []
    for claim in claims:
        chunk = find_chunk_for_claim(claim, chunks)
        if not chunk:
            continue
        metadata = chunk.get("metadata") or {}
        rels.append(
            relationship(
                claim_id(claim),
                "Claim",
                "GROUNDED_IN",
                chunk_node_id(str(chunk.get("chunk_id") or "")),
                "Chunk",
                {
                    "claim_id": claim.get("claim_id"),
                    "chunk_id": chunk.get("chunk_id"),
                    "section_id": chunk.get("section_id") or metadata.get("section_id"),
                    "document_id": chunk.get("document_id"),
                    "source_section": chunk.get("section"),
                },
            )
        )
    return rels


def relationships_from_entities(entities: list[dict]) -> list[dict]:
    rels: list[dict] = []
    for entity in entities:
        chunk_id = entity.get("chunk_id")
        entity_id = entity.get("entity_id")
        if not chunk_id or not entity_id:
            continue
        entity_type = str(entity.get("entity_type") or "entity")
        rels.append(
            relationship(
                chunk_node_id(str(chunk_id)),
                "Chunk",
                "CONTAINS_ENTITY",
                str(entity_id),
                entity_type,
                {
                    "entity_id": entity_id,
                    "entity_type": entity_type,
                    "value": entity.get("value"),
                    "normalized_value": entity.get("normalized_value"),
                    "chunk_id": chunk_id,
                },
            )
        )
    return rels


def relationships_from_chunks(chunks: list[dict]) -> list[dict]:
    rels: list[dict] = []
    seen_sections: set[tuple[str, str]] = set()
    for chunk in chunks:
        chunk_id = str(chunk.get("chunk_id") or "")
        if not chunk_id:
            continue
        metadata = chunk.get("metadata") or {}
        section_id_value = chunk.get("section_id") or metadata.get("section_id") or section_id_for_record(chunk)
        section_target = section_node_id(section_id_value)
        rels.append(
            relationship(
                chunk_node_id(chunk_id),
                "Chunk",
                "PART_OF",
                section_target,
                "Section",
                {
                    "chunk_id": chunk_id,
                    "section_id": section_id_value,
                    "section": chunk.get("section"),
                    "document_id": chunk.get("document_id"),
                },
            )
        )
        document_id = str(chunk.get("document_id") or "")
        if document_id:
            key = (document_id, section_target)
            if key not in seen_sections:
                seen_sections.add(key)
                rels.append(
                    relationship(
                        section_target,
                        "Section",
                        "FROM",
                        document_node_id(document_id),
                        "Document",
                        {
                            "section_id": section_id_value,
                            "section": chunk.get("section"),
                            "document_id": document_id,
                        },
                    )
                )
    return rels


def dedupe_relationships(relationships: list[dict]) -> list[dict]:
    seen: set[str] = set()
    unique: list[dict] = []
    for rel in relationships:
        rel_key = rel.get("relationship_id")
        if rel_key in seen:
            continue
        seen.add(rel_key)
        unique.append(rel)
    return unique


def derive_all_relationships(
    claims: list[dict],
    rules: list[dict],
    *,
    chunks: list[dict] | None = None,
    entities: list[dict] | None = None,
) -> list[dict]:
    relationships = relationships_from_claims(claims)
    relationships.extend(relationships_from_rules(rules))
    if chunks:
        relationships.extend(relationships_from_chunk_grounding(claims, chunks))
        relationships.extend(relationships_from_chunks(chunks))
    if entities:
        relationships.extend(relationships_from_entities(entities))
    return dedupe_relationships(relationships)


def main() -> None:
    parser = argparse.ArgumentParser(description="Derive graph relationships from claims and rules.")
    parser.add_argument("--claims-input", default="artifacts/claims/claims.jsonl", type=Path)
    parser.add_argument("--rules-input", default="artifacts/rules/rules_classified.jsonl", type=Path)
    parser.add_argument(
        "--rules-fallback",
        default="artifacts/rules/rules.jsonl",
        type=Path,
        help="Fallback rules file when classified rules are missing.",
    )
    parser.add_argument("--chunks-input", default="artifacts/chunks/chunks.jsonl", type=Path)
    parser.add_argument("--entities-input", default="artifacts/entities/entities.jsonl", type=Path)
    parser.add_argument("--output", default="artifacts/relationships/relationships.jsonl", type=Path)
    args = parser.parse_args()

    rules_path = args.rules_input if args.rules_input.exists() else args.rules_fallback
    relationships = derive_all_relationships(
        read_jsonl(args.claims_input),
        read_jsonl(rules_path),
        chunks=read_jsonl(args.chunks_input) if args.chunks_input.exists() else [],
        entities=read_jsonl(args.entities_input) if args.entities_input.exists() else [],
    )
    write_jsonl(relationships, args.output)
    print(f"Wrote {len(relationships)} relationships to {args.output}")


if __name__ == "__main__":
    main()
