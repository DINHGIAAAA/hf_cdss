import argparse
import hashlib
import json
import re
from pathlib import Path


CLAIM_PATTERNS = {
    "contraindication": (
        "contraindicated",
        "contraindication",
        "must not",
        "should not be used",
        "do not use",
    ),
    "renal_constraint": (
        "egfr",
        "renal impairment",
        "kidney impairment",
        "renal dysfunction",
        "dialysis",
    ),
    "usage_constraint": (
        "not recommended",
        "avoid use",
        "should not be used",
        "limitations of use",
    ),
    "hyperkalemia_risk": (
        "hyperkalemia",
        "hyperkalaemia",
        "serum potassium",
        "potassium",
    ),
    "dose_recommendation": (
        "recommended dose",
        "starting dose",
        "dose is",
        "dosage",
        "administer",
        "titrate",
    ),
    "drug_interaction": (
        "drug interactions",
        "concomitant",
        "coadministration",
        "inhibitor",
        "inducer",
    ),
    "adverse_reaction": (
        "adverse reaction",
        "adverse reactions",
        "bleeding",
        "hypotension",
        "hypoglycemia",
    ),
    "population_constraint": (
        "pregnancy",
        "lactation",
        "pediatric",
        "geriatric",
        "specific populations",
    ),
    "guideline_recommendation": (
        "recommend",
        "recommended",
        "should",
        "is indicated",
        "is useful",
        "benefit",
    ),
}

STRONG_MODAL_TERMS = (
    "contraindicated",
    "not recommended",
    "should not",
    "must not",
    "avoid",
    "recommended",
    "should",
    "may be",
    "is indicated",
)


def read_jsonl(path: Path) -> list[dict]:
    with path.open(encoding="utf-8-sig") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def write_jsonl(records: list[dict], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")


def sentence_split(text: str) -> list[str]:
    text = re.sub(r"\s+", " ", text or "").strip()
    if not text:
        return []
    sentences = re.split(r"(?<=[.!?])\s+(?=[A-Z0-9(])", text)
    return [sentence.strip() for sentence in sentences if len(sentence.strip()) >= 20]


def classify_claim(sentence: str, source_type: str) -> str | None:
    haystack = sentence.lower()
    ranked: list[tuple[int, str]] = []
    priority = {
        "contraindication": 0,
        "renal_constraint": 1,
        "usage_constraint": 2,
        "hyperkalemia_risk": 3,
        "drug_interaction": 4,
        "population_constraint": 5,
        "dose_recommendation": 6,
        "adverse_reaction": 7,
        "guideline_recommendation": 8,
    }
    for claim_type, terms in CLAIM_PATTERNS.items():
        if claim_type == "guideline_recommendation" and source_type != "guideline":
            continue
        if any(term in haystack for term in terms):
            ranked.append((priority.get(claim_type, 99), claim_type))
    if not ranked:
        return None
    ranked.sort(key=lambda item: item[0])
    return ranked[0][1]


def confidence(sentence: str, claim_type: str, source_type: str) -> float:
    haystack = sentence.lower()
    score = 0.75
    if any(term in haystack for term in STRONG_MODAL_TERMS):
        score += 0.15
    if claim_type in {"contraindication", "renal_constraint"}:
        score += 0.05
    if source_type == "drug_label":
        score += 0.05
    return min(round(score, 2), 1.0)


def claim_id(record: dict, sentence: str, index: int) -> str:
    raw = f"{record.get('document_id')}|{record.get('section')}|{index}|{sentence}"
    digest = hashlib.sha1(raw.encode("utf-8")).hexdigest()[:12]
    return f"claim_{digest}"


def create_claim_regex(record: dict, sentence: str, index: int) -> dict | None:
    claim_type = classify_claim(sentence, record.get("source_type", ""))
    if claim_type is None:
        return None

    metadata = record.get("metadata") or {}
    output = {
        "claim_id": claim_id(record, sentence, index),
        "document_id": metadata.get("source_id") or record.get("document_id"),
        "source_type": record.get("source_type"),
        "claim": sentence,
        "claim_type": claim_type,
        "source_section": record.get("section"),
        "evidence": sentence,
        "confidence": confidence(sentence, claim_type, record.get("source_type", "")),
        "conditions": {},
        "metadata": {
            "source_id": metadata.get("source_id") or record.get("document_id"),
            "source": metadata.get("source"),
            "source_url": metadata.get("source_url"),
            "publisher": metadata.get("publisher"),
            "title": metadata.get("title"),
            "citation": metadata.get("citation"),
            "license_note": metadata.get("license_note"),
            "source_file": metadata.get("source_file"),
            "matched_important_topics": metadata.get("matched_important_topics", []),
            "extraction_method": "regex",
        },
    }

    if record.get("source_type") == "drug_label":
        drug = metadata.get("drug")
        if drug:
            output["drug"] = drug
        else:
            output["drug"] = None
            output["claim_type"] = "general_monitoring"
        output["metadata"]["published_date"] = metadata.get("published_date")
        output["metadata"]["setid"] = metadata.get("setid")
    else:
        output["guideline_topic"] = metadata.get("guideline_topic")
        output["metadata"]["page_start"] = metadata.get("page_start")
        output["metadata"]["page_end"] = metadata.get("page_end")

    return output


def dedupe_claims_by_id(claims: list[dict]) -> list[dict]:
    seen: set[str] = set()
    unique: list[dict] = []
    for claim in claims:
        claim_key = claim.get("claim_id")
        if claim_key in seen:
            continue
        seen.add(claim_key)
        unique.append(claim)
    return unique


def claims_from_records(records: list[dict], max_claims_per_section: int) -> list[dict]:
    from scraper.semantic.claim_extraction import extract_claims_batch
    from scraper.semantic.dedup import dedupe_claims

    claims = dedupe_claims(extract_claims_batch(records))

    llm_evidence = {claim.get("evidence", "").lower().strip() for claim in claims}
    for record in records:
        section_claims_count = sum(
            1
            for claim in claims
            if claim.get("document_id") == record.get("document_id")
            and claim.get("source_section") == record.get("section")
        )
        for index, sentence in enumerate(sentence_split(record.get("text", "")), start=1):
            if sentence.lower().strip() in llm_evidence:
                continue
            claim = create_claim_regex(record, sentence, index)
            if claim:
                claims.append(claim)
                section_claims_count += 1
            if section_claims_count >= max_claims_per_section:
                break

    return dedupe_claims(dedupe_claims_by_id(claims))


def main() -> None:
    parser = argparse.ArgumentParser(description="Create claims from important sections.")
    parser.add_argument("--input", default="processed/sections/important_sections.jsonl", type=Path)
    parser.add_argument("--output", default="artifacts/claims/claims.jsonl", type=Path)
    parser.add_argument("--max-claims-per-section", default=40, type=int)
    args = parser.parse_args()

    claims = claims_from_records(read_jsonl(args.input), args.max_claims_per_section)
    write_jsonl(claims, args.output)
    print(f"Wrote {len(claims)} claims to {args.output}")


if __name__ == "__main__":
    main()
