import argparse
import json
import re
from pathlib import Path

from kafka import KafkaConsumer, KafkaProducer
from kafka.errors import KafkaError

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


def filter_important_sections(records: list[dict]) -> list[dict]:
    important: list[dict] = []
    for record in records:
        if record.get("source_type") == "drug_label":
            matches = drug_matches(record)
        elif record.get("source_type") == "guideline":
            matches = guideline_matches(record)
        else:
            matches = []
        if matches:
            important.append(mark_record(record, matches))
    return important


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
    parser = argparse.ArgumentParser(description="Filter important clinical sections (batch file or Kafka).")
    parser.add_argument("--sections-dir", default="processed/sections", type=Path)
    parser.add_argument("--output", default="processed/sections/important_sections.jsonl", type=Path)
    parser.add_argument("--kafka-bootstrap-servers", default="localhost:9092", help="Kafka bootstrap servers.")
    parser.add_argument("--consumer-topic", default="sections_parsed", help="Kafka topic to consume parsed sections from.")
    parser.add_argument("--producer-topic", default="important_sections", help="Kafka topic to produce important sections to.")
    parser.add_argument("--consumer-group-id", default="filtering_service", help="Kafka consumer group ID.")
    parser.add_argument("--mode", choices=["auto", "file", "kafka"], default="auto")
    args = parser.parse_args()

    use_file = args.mode == "file" or (
        args.mode == "auto" and any(collect_section_files(args.sections_dir))
    )
    if use_file:
        records: list[dict] = []
        for path in collect_section_files(args.sections_dir):
            records.extend(read_jsonl(path))
        records = dedupe_sections(records)
        important = filter_important_sections(records)
        write_jsonl(important, args.output)
        print(f"Wrote {len(important)} important sections to {args.output}")
        return

    print(f"Connecting to Kafka at {args.kafka_bootstrap_servers}...")
    try:
        consumer = KafkaConsumer(
            args.consumer_topic,
            bootstrap_servers=args.kafka_bootstrap_servers,
            group_id=args.consumer_group_id,
            auto_offset_reset='earliest',
            value_deserializer=lambda m: json.loads(m.decode('utf-8'))
        )
        producer = KafkaProducer(
            bootstrap_servers=args.kafka_bootstrap_servers,
            value_serializer=lambda m: json.dumps(m, ensure_ascii=False).encode('utf-8')
        )
    except KafkaError as e:
        print(f"\nFATAL: Could not connect to Kafka. Is it running? Details: {e}")
        return

    print(f"Listening for messages on topic '{args.consumer_topic}'... (Press Ctrl+C to stop)")
    try:
        for message in consumer:
            record = message.value
            if record.get("source_type") == "drug_label":
                matches = drug_matches(record)
            elif record.get("source_type") == "guideline":
                matches = guideline_matches(record)
            else:
                matches = []
            
            if matches:
                important_record = mark_record(record, matches)
                producer.send(args.producer_topic, value=important_record)
                print(f"  -> Found important section in '{record.get('document_id')}', forwarding to '{args.producer_topic}'")
    except KeyboardInterrupt:
        print("\nShutting down...")
    finally:
        producer.flush()
        producer.close()
        consumer.close()
        print("Kafka connections closed.")


if __name__ == "__main__":
    main()
