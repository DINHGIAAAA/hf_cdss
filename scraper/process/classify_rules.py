import argparse
import json
from pathlib import Path

from kafka import KafkaConsumer, KafkaProducer
from kafka.errors import KafkaError
from scraper.kafka_utils import connect_kafka_with_retry


HARD_BLOCK_ACTIONS = {"contraindicated", "avoid", "not_recommended"}


def rule_tier(rule: dict) -> str:
    condition = rule.get("condition") or {}
    action = rule.get("action")

    if condition:
        return "usable_rules"
    if action in HARD_BLOCK_ACTIONS:
        return "needs_condition_refinement"
    return "rejected_rules"


def annotate(rule: dict, tier: str) -> dict:
    output = dict(rule)
    output["safety_tier"] = tier
    output["recommendation_use"] = "hard_rule" if tier == "usable_rules" else "warning_only"
    if tier == "rejected_rules":
        output["recommendation_use"] = "do_not_use"
    return output


def classify_rules(records: list[dict]) -> list[dict]:
    return [annotate(rule, rule_tier(rule)) for rule in records]


def main() -> None:
    parser = argparse.ArgumentParser(description="Classify generated rules (batch file or Kafka).")
    parser.add_argument("--input", default="artifacts/rules/rules.jsonl", type=Path)
    parser.add_argument("--output", default="artifacts/rules/rules_classified.jsonl", type=Path)
    parser.add_argument("--kafka-bootstrap-servers", default="localhost:9092")
    parser.add_argument("--consumer-topic", default="rules_generated")
    parser.add_argument("--producer-topic", default="rules_classified")
    parser.add_argument("--consumer-group-id", default="rule_classification_service")
    parser.add_argument("--mode", choices=["auto", "file", "kafka"], default="auto")
    args = parser.parse_args()

    use_file = args.mode == "file" or (args.mode == "auto" and args.input.exists())
    if use_file:
        rules = []
        with args.input.open(encoding="utf-8-sig") as handle:
            for line in handle:
                line = line.strip()
                if line:
                    rules.append(json.loads(line))
        classified = classify_rules(rules)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open("w", encoding="utf-8", newline="\n") as handle:
            for rule in classified:
                handle.write(json.dumps(rule, ensure_ascii=False) + "\n")
        print(f"Wrote {len(classified)} classified rules to {args.output}")
        return

    print(f"Connecting to Kafka at {args.kafka_bootstrap_servers}...")
    def _connect():
        return (
            KafkaConsumer(
                args.consumer_topic, bootstrap_servers=args.kafka_bootstrap_servers,
                group_id=args.consumer_group_id, auto_offset_reset='earliest',
                value_deserializer=lambda m: json.loads(m.decode('utf-8'))
            ),
            KafkaProducer(bootstrap_servers=args.kafka_bootstrap_servers, value_serializer=lambda m: json.dumps(m, ensure_ascii=False).encode('utf-8'))
        )
    consumer, producer = connect_kafka_with_retry(_connect)

    print(f"Listening for messages on topic '{args.consumer_topic}'... (Press Ctrl+C to stop)")
    try:
        for message in consumer:
            rule = message.value
            tier = rule_tier(rule)
            annotated_rule = annotate(rule, tier)
            producer.send(args.producer_topic, value=annotated_rule)
            print(f"  -> Classified rule '{rule.get('rule_id')}' as '{tier}', forwarding to '{args.producer_topic}'")
    except KeyboardInterrupt:
        print("\nShutting down...")
    finally:
        producer.flush()
        producer.close()
        consumer.close()
        print("Kafka connections closed.")


if __name__ == "__main__":
    main()
