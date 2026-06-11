import argparse
import json
import re
from pathlib import Path


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
    value = re.sub(r"\s+", " ", value or "")
    return value.strip().upper()


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


def main() -> None:
    parser = argparse.ArgumentParser(description="Extract important sections from parsed drug labels and guidelines.")
    parser.add_argument(
        "--inputs",
        nargs="+",
        default=[
            "processed/sections/drug_label_sections.jsonl",
            "processed/sections/guideline_sections.jsonl",
        ],
        type=Path,
    )
    parser.add_argument("--output", default="processed/sections/important_sections.jsonl", type=Path)
    args = parser.parse_args()

    important = []
    for input_path in [Path(path) for path in args.inputs]:
        for record in read_jsonl(input_path):
            if record.get("source_type") == "drug_label":
                matches = drug_matches(record)
            elif record.get("source_type") == "guideline":
                matches = guideline_matches(record)
            else:
                matches = []

            if matches:
                important.append(mark_record(record, matches))

    write_jsonl(important, args.output)
    print(f"Wrote {len(important)} important sections to {args.output}")


if __name__ == "__main__":
    main()
