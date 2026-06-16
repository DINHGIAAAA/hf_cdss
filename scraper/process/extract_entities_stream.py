"""A streaming service to extract entities from chunks received via Kafka.

This service consumes chunk messages, applies regex-based entity extraction,
enriches the message with the found entities, and produces it to a new topic.
"""
import argparse
import hashlib
import json
import re

from kafka import KafkaConsumer, KafkaProducer
from kafka.errors import KafkaError


# Re-using the same patterns from the batch script
ENTITY_PATTERNS = {
    "lab": (
        r"\beGFR\b",
        r"\bserum potassium\b",
        r"\bpotassium\b",
        r"\bcreatinine\b",
        r"\bHbA1c\b",
        r"\bblood pressure\b",
    ),
    "condition": (
        r"\bheart failure\b",
        r"\bchronic kidney disease\b",
        r"\bCKD\b",
        r"\bdiabetes mellitus\b",
        r"\btype 2 diabetes\b",
        r"\bhypertension\b",
        r"\batrial fibrillation\b",
        r"\bhyperkalemia\b",
        r"\brenal impairment\b",
        r"\brenal dysfunction\b",
        r"\bcardiogenic shock\b",
        r"\bbleeding\b",
    ),
    "action": (
        r"\bnot recommended\b",
        r"\bcontraindicated\b",
        r"\bavoid\b",
        r"\brecommended\b",
        r"\bmonitor\b",
        r"\badjust\b",
        r"\btitrate\b",
    ),
    "threshold": (
        r"\beGFR\s*(?:is\s*)?(?:less than|below|<|≤|<=)\s*\d+",
        r"\bserum potassium\s*(?:is\s*)?(?:greater than|above|>|≥|>=)\s*\d+(?:\.\d+)?",
        r"\bpotassium\s*(?:is\s*)?(?:greater than|above|>|≥|>=)\s*\d+(?:\.\d+)?",
        r"\b\d+(?:\.\d+)?\s*(?:mL/min/1\.73\s*m\s*2|mg/dL|mmol/L)\b",
    ),
}


def entity_id(entity_type: str, value: str) -> str:
    normalized = re.sub(r"\s+", " ", value.lower()).strip()
    digest = hashlib.sha1(f"{entity_type}|{normalized}".encode("utf-8")).hexdigest()[:12]
    return f"{entity_type}_{digest}"


def extract_drug_entity(chunk: dict) -> list[dict]:
    metadata = chunk.get("metadata") or {}
    drug = metadata.get("drug")
    if not drug:
        return []
    return [
        {
            "entity_id": entity_id("drug", drug),
            "entity_type": "drug",
            "value": drug,
            "normalized_value": drug.lower(),
            "chunk_id": chunk.get("chunk_id"),
            "document_id": chunk.get("document_id"),
        }
    ]


def extract_entities(chunk: dict) -> list[dict]:
    text = chunk.get("text", "")
    entities = extract_drug_entity(chunk)

    for entity_type, patterns in ENTITY_PATTERNS.items():
        for pattern in patterns:
            for match in re.finditer(pattern, text, flags=re.IGNORECASE):
                value = match.group(0)
                entities.append(
                    {
                        "entity_id": entity_id(entity_type, value),
                        "entity_type": entity_type,
                        "value": value,
                        "normalized_value": re.sub(r"\s+", " ", value.lower()).strip(),
                        "chunk_id": chunk.get("chunk_id"),
                        "document_id": chunk.get("document_id"),
                        "start_char": match.start(),
                        "end_char": match.end(),
                    }
                )
    return entities


def main() -> None:
    parser = argparse.ArgumentParser(description="A streaming service to extract entities from chunks.")
    parser.add_argument("--kafka-bootstrap-servers", default="localhost:9092")
    parser.add_argument("--consumer-topic", default="chunks_to_index")
    parser.add_argument("--producer-topic", default="chunks_with_entities")
    parser.add_argument("--consumer-group-id", default="entity_extraction_service")
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
            chunk = message.value
            document_id = chunk.get("document_id", "unknown_doc")
            
            # Extract entities and enrich the message
            entities = extract_entities(chunk)
            chunk["entities"] = entities
            
            # Produce the enriched message to the next topic
            producer.send(args.producer_topic, value=chunk)
            print(f"  -> Processed chunk from '{document_id}', found {len(entities)} entities. Forwarding to '{args.producer_topic}'")

    except KeyboardInterrupt:
        print("\nShutting down...")
    finally:
        producer.flush()
        producer.close()
        consumer.close()
        print("Kafka connections closed.")


if __name__ == "__main__":
    main()