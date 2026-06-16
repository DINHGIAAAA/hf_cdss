import argparse
import json
from pathlib import Path

from kafka import KafkaConsumer, KafkaProducer
from kafka.errors import KafkaError


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


def main() -> None:
    parser = argparse.ArgumentParser(description="A streaming service to classify generated rules.")
    parser.add_argument("--kafka-bootstrap-servers", default="localhost:9092")
    parser.add_argument("--consumer-topic", default="rules_generated")
    parser.add_argument("--producer-topic", default="rules_classified")
    parser.add_argument("--consumer-group-id", default="rule_classification_service")
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
