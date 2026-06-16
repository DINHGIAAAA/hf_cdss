import argparse
import hashlib
import json
import re
from pathlib import Path

from kafka import KafkaConsumer, KafkaProducer
from kafka.errors import KafkaError


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
    sentences = re.split(r"(?<=[.!?])\s+(?=[A-Z0-9])", text)
    return [sentence.strip() for sentence in sentences if len(sentence.strip()) >= 40]


def classify_claim(sentence: str, source_type: str) -> str | None:
    haystack = sentence.lower()
    for claim_type, terms in CLAIM_PATTERNS.items():
        if claim_type == "guideline_recommendation" and source_type != "guideline":
            continue
        if any(term in haystack for term in terms):
            return claim_type
    return None


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


def create_claim(record: dict, sentence: str, index: int) -> dict | None:
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
        },
    }

    if record.get("source_type") == "drug_label":
        # Only assign drug if explicitly found; don't use document_id as fallback
        drug = metadata.get("drug")
        if drug:
            output["drug"] = drug
        else:
            # No drug found - mark as general monitoring
            output["drug"] = None
            output["claim_type"] = "general_monitoring"
        output["metadata"]["published_date"] = metadata.get("published_date")
        output["metadata"]["setid"] = metadata.get("setid")
    else:
        output["guideline_topic"] = metadata.get("guideline_topic")
        output["metadata"]["page_start"] = metadata.get("page_start")
        output["metadata"]["page_end"] = metadata.get("page_end")

    return output


def main() -> None:
    parser = argparse.ArgumentParser(description="A streaming service to create claims from important sections.")
    parser.add_argument("--kafka-bootstrap-servers", default="localhost:9092")
    parser.add_argument("--consumer-topic", default="important_sections")
    parser.add_argument("--producer-topic", default="claims_created")
    parser.add_argument("--consumer-group-id", default="claim_creation_service")
    parser.add_argument("--max-claims-per-section", default=8, type=int)
    args = parser.parse_args()

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
            section_claims_count = 0
            for index, sentence in enumerate(sentence_split(record.get("text", "")), start=1):
                claim = create_claim(record, sentence, index)
                if claim:
                    producer.send(args.producer_topic, value=claim)
                    section_claims_count += 1
                    if section_claims_count >= args.max_claims_per_section:
                        break
            if section_claims_count > 0:
                print(f"  -> Created {section_claims_count} claims from section in '{record.get('document_id')}', forwarding to '{args.producer_topic}'")
    except KeyboardInterrupt:
        print("\nShutting down...")
    finally:
        producer.flush()
        producer.close()
        consumer.close()
        print("Kafka connections closed.")


if __name__ == "__main__":
    main()
