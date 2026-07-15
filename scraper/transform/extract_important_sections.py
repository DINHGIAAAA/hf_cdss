from scraper.io.jsonl import read_jsonl, write_jsonl
import argparse
import json
import logging
import re
from pathlib import Path

from scraper.transform.text_normalization import normalize_inline_text

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(message)s")

DRUG_SECTION_ALIASES = {
    "INDICATIONS AND USAGE": {"INDICATIONS AND USAGE", "INDICATIONS & USAGE"},
    "DOSAGE AND ADMINISTRATION": {"DOSAGE AND ADMINISTRATION", "DOSAGE & ADMINISTRATION"},
    "CONTRAINDICATIONS": {"CONTRAINDICATIONS"},
    "WARNINGS AND PRECAUTIONS": {"WARNINGS AND PRECAUTIONS", "WARNINGS", "BOXED WARNING"},
    "ADVERSE REACTIONS": {"ADVERSE REACTIONS"},
    "DRUG INTERACTIONS": {"DRUG INTERACTIONS"},
    "USE IN SPECIFIC POPULATIONS": {"USE IN SPECIFIC POPULATIONS"},
    "RENAL IMPAIRMENT": {"RENAL IMPAIRMENT"},
}

GUIDELINE_TOPICS = {
    "recommendations": ("recommendation", "recommendations", "cor loe", "class of recommendation"),
    "drug therapy": ("drug therapy", "pharmacologic", "pharmacological", "medication", "treatment with"),
    "dosing": (
        "dosing",
        "dose adjustment",
        "dose titration",
        "titration",
        "starting dose",
        "target dose",
        "maintenance dose",
    ),
    "monitoring": (
        "monitoring",
        "laboratory monitoring",
        "follow-up",
        "renal function test",
        "lab monitoring",
        "safety monitoring",
    ),
    "drug interactions": (
        "drug interaction",
        "drug-drug",
        "drug–drug",
        "concomitant use",
        "co-administration",
        "coadministration",
    ),
    "warnings": (
        "warning",
        "boxed warning",
        "black box",
        "precaution",
        "risk of",
        "serious risk",
    ),
    "contraindications": ("contraindication", "contraindications", "contraindicated"),
    "comorbidities": ("comorbidity", "comorbidities", "coexisting", "concomitant"),
    "renal dysfunction": (
        "renal dysfunction",
        "kidney dysfunction",
        "worsening renal",
        "egfr",
        "ckd",
        "renal impairment",
        "hepatic impairment",
    ),
    "hyperkalemia": ("hyperkalemia", "hyperkalaemia", "serum potassium", "potassium"),
    "atrial fibrillation": ("atrial fibrillation", "afib", "af "),
    "diabetes": ("diabetes", "diabetic", "glycemic", "glycaemic", "hba1c"),
    "hypertension": ("hypertension", "blood pressure", "antihypertensive"),
}

def normalize(value: str) -> str:
    return normalize_inline_text(value).upper()

def drug_matches(record: dict) -> list[str]:
    section = normalize(record.get("section", ""))
    text = normalize(record.get("text", ""))
    matches = []

    for canonical, aliases in DRUG_SECTION_ALIASES.items():
        if section in aliases:
            matches.append(canonical)
            continue
        if canonical == "RENAL IMPAIRMENT" and "RENAL IMPAIRMENT" in text:
            matches.append(canonical)

    return matches

def guideline_matches(record: dict) -> list[str]:
    haystack = f"{record.get('section', '')} {record.get('text', '')}".lower()
    return [
        topic
        for topic, terms in GUIDELINE_TOPICS.items()
        if any(term in haystack for term in terms)
    ]

from scraper.kg.identifiers import section_id_for_record

def mark_record(record: dict, matched_topics: list[str]) -> dict:
    output = dict(record)
    metadata = dict(output.get("metadata") or {})
    metadata["matched_important_topics"] = matched_topics
    section_id_value = section_id_for_record(output)
    metadata["section_id"] = section_id_value
    output["section_id"] = section_id_value
    output["metadata"] = metadata
    return output

def dedupe_sections(records: list[dict]) -> list[dict]:
    seen: set[tuple] = set()
    unique: list[dict] = []
    for record in records:
        key = (
            record.get("document_id"),
            record.get("section"),
            (record.get("text") or "")[:500],
        )
        if key in seen:
            continue
        seen.add(key)
        unique.append(record)
    return unique

def collect_section_files(sections_dir: Path) -> list[Path]:
    candidates = [
        sections_dir / "guideline_sections.jsonl",
        sections_dir / "guideline_html_sections.jsonl",
        sections_dir / "drug_label_sections.jsonl",
    ]
    return [path for path in candidates if path.exists()]

def main() -> None:
    parser = argparse.ArgumentParser(description="Filter important clinical sections from parsed guideline and label sections.")
    parser.add_argument("--sections-dir", default="processed/sections", type=Path)
    parser.add_argument("--output", default="processed/sections/important_sections.jsonl", type=Path)
    args = parser.parse_args()

    records: list[dict] = []
    for path in collect_section_files(args.sections_dir):
        loaded = read_jsonl(path)
        records.extend(loaded)
        logger.info("Loaded %s sections from %s", len(loaded), path.name)
    records = dedupe_sections(records)
    logger.info("Total %s unique sections to filter", len(records))

    from scraper.semantic.section_filter import filter_important_sections

    important = filter_important_sections(records)
    write_jsonl(important, args.output)
    print(f"Wrote {len(important)} important sections to {args.output}")

if __name__ == "__main__":
    main()
