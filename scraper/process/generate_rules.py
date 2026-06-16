import argparse
import hashlib
import json
import re
from pathlib import Path

from kafka import KafkaConsumer, KafkaProducer
from kafka.errors import KafkaError


def read_jsonl(path: Path) -> list[dict]:
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


def rule_id(parts: list[str]) -> str:
    base = "_".join(slug(part) for part in parts if part)
    digest = hashlib.sha1(base.encode("utf-8")).hexdigest()[:8]
    return f"{base[:72]}_{digest}"


def parse_egfr_condition(text: str) -> str | None:
    patterns = [
        r"egfr\s*(?:is\s*)?(?:less than|below|<)\s*(\d+)",
        r"egfr\s*(?:of\s*)?(\d+)\s*(?:to|-)\s*(\d+)",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match and len(match.groups()) == 1:
            return f"<{match.group(1)}"
        if match and len(match.groups()) == 2:
            return f"{match.group(1)}-{match.group(2)}"
    return None


def parse_potassium_condition(text: str) -> str | None:
    match = re.search(
        r"(?:serum\s+)?potassium\s*(?:is\s*)?(?:greater than|above|>|>=|≥)\s*(\d+(?:\.\d+)?)",
        text,
        flags=re.IGNORECASE,
    )
    if match:
        return f">{match.group(1)}"
    return None


def infer_indication(text: str) -> str | None:
    haystack = text.lower()
    if "glycemic control" in haystack or "glycaemic control" in haystack:
        return "glycemic_control"
    if "heart failure" in haystack:
        return "heart_failure"
    if "hypertension" in haystack or "blood pressure" in haystack:
        return "hypertension"
    if "atrial fibrillation" in haystack:
        return "atrial_fibrillation"
    if "chronic kidney disease" in haystack or "ckd" in haystack:
        return "chronic_kidney_disease"
    return None


def infer_patient_group(text: str) -> dict:
    haystack = text.lower()
    if "type 1 diabetes" in haystack or "type 1 diabetes mellitus" in haystack:
        return {"diabetes_type": "type_1"}
    return {}


def infer_action(text: str, claim_type: str) -> str:
    haystack = text.lower()
    if "contraindicated" in haystack or claim_type == "contraindication":
        return "contraindicated"
    if "not recommended" in haystack:
        return "not_recommended"
    if "avoid" in haystack:
        return "avoid"
    if "monitor" in haystack:
        return "monitor"
    if "recommended" in haystack or "should" in haystack:
        return "recommended"
    return "review"


def infer_reason(text: str, action: str, condition: dict) -> str:
    haystack = text.lower()
    if condition.get("egfr") and condition.get("indication") == "glycemic_control":
        return f"Likely ineffective for glycemic control when eGFR {condition['egfr']}"
    if condition.get("potassium"):
        return f"Potassium-related safety constraint when potassium {condition['potassium']}"
    if action == "contraindicated":
        return "Source states this use or condition is contraindicated"
    if "renal" in haystack or "kidney" in haystack or "egfr" in haystack:
        return "Renal function constraint from source evidence"
    return "Rule generated from source claim evidence"


def generate_rule(claim: dict) -> dict | None:
    text = claim.get("claim") or claim.get("evidence") or ""
    claim_type = claim.get("claim_type", "")
    condition = {}

    egfr = parse_egfr_condition(text)
    potassium = parse_potassium_condition(text)
    indication = infer_indication(text)

    if egfr:
        condition["egfr"] = egfr
    if potassium:
        condition["potassium"] = potassium
    if indication:
        condition["indication"] = indication
    condition.update(infer_patient_group(text))

    rule_worthy_types = {
        "contraindication",
        "renal_constraint",
        "usage_constraint",
        "hyperkalemia_risk",
        "drug_interaction",
        "population_constraint",
    }
    # Exclude general_monitoring - these are not drug-specific enough for constraints
    if claim_type == "general_monitoring":
        return None
    if claim_type not in rule_worthy_types:
        return None
    if not condition and claim_type not in {"contraindication", "drug_interaction", "population_constraint"}:
        return None

    # Drug must be present and not None for a usable rule
    drug = claim.get("drug")
    if not drug:
        return None
    action = infer_action(text, claim_type)
    haystack = text.lower()
    if claim_type == "usage_constraint" and any(term in haystack for term in ("monitoring", "assay", "test is not recommended", "tests is not recommended")):
        return None
    if action == "review" and not {"egfr", "potassium"} & set(condition):
        return None

    source_refs = {
        "claim_id": claim.get("claim_id"),
        "document_id": claim.get("document_id"),
        "source_type": claim.get("source_type"),
        "source_section": claim.get("source_section"),
        "evidence": claim.get("evidence"),
        "confidence": claim.get("confidence"),
        "metadata": claim.get("metadata") or {},
    }

    return {
        "rule_id": rule_id([drug, claim_type, action, json.dumps(condition, sort_keys=True)]),
        "drug": drug,
        "condition": condition,
        "action": action,
        "reason": infer_reason(text, action, condition),
        "claim_type": claim_type,
        "source_refs": [source_refs],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="A streaming service to generate rules from claims.")
    parser.add_argument("--kafka-bootstrap-servers", default="localhost:9092")
    parser.add_argument("--consumer-topic", default="claims_created")
    parser.add_argument("--producer-topic", default="rules_generated")
    parser.add_argument("--consumer-group-id", default="rule_generation_service")
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
            claim = message.value
            rule = generate_rule(claim)
            if rule:
                producer.send(args.producer_topic, value=rule)
                print(f"  -> Generated rule '{rule.get('rule_id')}' from claim '{claim.get('claim_id')}', forwarding to '{args.producer_topic}'")
    except KeyboardInterrupt:
        print("\nShutting down...")
    finally:
        producer.flush()
        producer.close()
        consumer.close()
        print("Kafka connections closed.")


if __name__ == "__main__":
    main()
