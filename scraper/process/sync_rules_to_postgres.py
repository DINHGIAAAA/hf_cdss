"""A streaming service to sync generated rules from Kafka to PostgreSQL.

This service consumes rules from the 'rules_generated' topic, converts them
into the 'constraint_rules' table format, and handles versioning based on
content changes. New rule versions are inserted as 'draft' for review.
"""
import argparse
import json
import sys
from pathlib import Path

# Add project root to path to allow backend imports.
# This assumes the script is run from the project root.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from kafka import KafkaConsumer
from kafka.errors import KafkaError

# Import conversion logic from the batch script.
# We reuse this logic to maintain consistency.
from scraper.process.sync_constraints_to_postgres import (
    convert_rule_to_constraint,
)

# Import database functions from the backend application.
try:
    from app.modules.datastores.postgres import (
        insert_constraint_rule,
        get_latest_constraint_rule_version,
    )
except ImportError as e:
    print(f"FATAL: Could not import backend modules. Make sure PYTHONPATH is set correctly.")
    print(f"Details: {e}")
    sys.exit(1)


def process_rule(rule: dict):
    """
    Processes a single rule: converts it, checks for version changes,
    and inserts a new version into PostgreSQL if needed.
    """
    try:
        drug = rule.get("drug")
        if not drug:
            print(f"  -> Skipping rule {rule.get('rule_id')} because it has no drug.")
            return

        # 1. Convert the generated rule into the database constraint format.
        new_constraint = convert_rule_to_constraint(rule)
        constraint_id = new_constraint["constraint_id"]
        new_hash = new_constraint["metadata"]["content_hash"]

        # 2. Check for the latest existing version of this rule in the database.
        latest_version = get_latest_constraint_rule_version(constraint_id)

        if latest_version:
            # Rule exists, check if content has changed.
            latest_hash = latest_version.get("metadata", {}).get("content_hash")
            if latest_hash == new_hash:
                # No change in content, skip.
                print(f"  -> Rule '{constraint_id}' is unchanged (version {latest_version['version']}). Skipping.")
                return

            # Content has changed, so we create a new version.
            new_constraint["version"] = latest_version["version"] + 1
            print(f"  -> Detected content change for rule '{constraint_id}'. Creating new version {new_constraint['version']}...")
        else:
            # This is the first time we've seen this rule.
            new_constraint["version"] = 1
            print(f"  -> New rule '{constraint_id}' detected. Creating version 1...")

        # 4. Insert the new version with 'draft' status for admin review.
        if insert_constraint_rule(new_constraint):
            print(f"     Successfully inserted rule '{constraint_id}' version {new_constraint['version']} as 'draft'.")
        else:
            print(f"     ERROR: Failed to insert new version for rule '{constraint_id}'.")

    except Exception as e:
        print(f"\nERROR processing rule {rule.get('rule_id')}: {e}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Kafka to PostgreSQL Rule Sync Service.")
    # Kafka Args
    parser.add_argument("--kafka-bootstrap-servers", default="localhost:9092")
    parser.add_argument("--consumer-topic", default="rules_classified", help="Topic with classified rules.")
    parser.add_argument("--consumer-group-id", default="postgres_rule_sync_service")
    args = parser.parse_args()

    # Note: Database connection is handled by the imported postgres functions,
    # which rely on environment variables (see app/core/config.py).

    print(f"Connecting to Kafka at {args.kafka_bootstrap_servers}...")
    try:
        consumer = KafkaConsumer(
            args.consumer_topic,
            bootstrap_servers=args.kafka_bootstrap_servers,
            group_id=args.consumer_group_id,
            auto_offset_reset='earliest',
            # Auto-commit is fine here as processing is idempotent.
            # If a message is re-processed, the content hash check will prevent duplicates.
            value_deserializer=lambda m: json.loads(m.decode('utf-8')),
        )
    except KafkaError as e:
        print(f"\nFATAL: Could not connect to Kafka. Is it running? Details: {e}")
        return

    print(f"Listening for messages on topic '{args.consumer_topic}'... (Press Ctrl+C to stop)")
    try:
        for message in consumer:
            rule = message.value
            # Only process rules that are not rejected by the classification step.
            # This prevents cluttering the database with rules that are not useful.
            if rule.get("safety_tier") == "rejected_rules":
                print(f"  -> Skipping rejected rule '{rule.get('rule_id')}'.")
                continue
            process_rule(rule)

    except KeyboardInterrupt:
        print("\nShutting down...")
    finally:
        consumer.close()
        print("Kafka consumer closed.")


if __name__ == "__main__":
    # This check ensures the script is run in a context where backend modules are accessible.
    try:
        from app.core.config import settings
        print(f"Database host: {settings.POSTGRES_SERVER}")
    except (ImportError, AttributeError):
        print("\nCould not import backend settings. Make sure the script is run from the project root, e.g.:")
        print("python -m scraper.process.sync_rules_to_postgres")
        sys.exit(1)

    main()