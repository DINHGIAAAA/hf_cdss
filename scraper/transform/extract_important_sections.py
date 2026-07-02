import argparse
import json
import re
from pathlib import Path

from scraper.transform.text_normalization import normalize_inline_text


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
    "recommendations": ("recommendation", "recommendations", "cor loe"),
    "drug therapy": ("drug therapy", "pharmacologic", "pharmacological", "medication", "treatment with"),
    "contraindications": ("contraindication", "contraindications", "contraindicated"),
    "comorbidities": ("comorbidity", "comorbidities", "coexisting", "concomitant"),
    "renal dysfunction": ("renal dysfunction", "kidney dysfunction", "worsening renal", "egfr", "ckd"),
    "hyperkalemia": ("hyperkalemia", "hyperkalaemia", "serum potassium", "potassium"),
    "atrial fibrillation": ("atrial fibrillation", "afib", "af "),
    "diabetes": ("diabetes", "diabetic", "glycemic", "glycaemic", "hba1c"),
    "hypertension": ("hypertension", "blood pressure", "antihypertensive"),
}


def normalize(value: str) -> str:
    return normalize_inline_text(value).upper()


def read_jsonl(path: Path) -> list[dict]:
    with path.open(encoding="utf-8-sig") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def write_jsonl(records: list[dict], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")


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


def mark_record(record: dict, matched_topics: list[str]) -> dict:
    output = dict(record)
    metadata = dict(output.get("metadata") or {})
    metadata["matched_important_topics"] = matched_topics
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
        records.extend(read_jsonl(path))
    records = dedupe_sections(records)

    from scraper.semantic.section_filter import filter_important_sections

    important = filter_important_sections(records)
    write_jsonl(important, args.output)
    print(f"Wrote {len(important)} important sections to {args.output}")


if __name__ == "__main__":
    main()
