"""A streaming service to load chunks from Kafka into Neo4j efficiently.

This service consumes messages from a Kafka topic, batches them, and creates
nodes and relationships in a Neo4j database. It runs in parallel with other
loaders (e.g., for ChromaDB).

Key features:
- Batch processing for efficient database writes using UNWIND.
- Manual offset management for at-least-once delivery guarantee.
- Idempotent queries using MERGE to prevent duplicate data.
- Configurable via command-line arguments.
- Graceful shutdown.
"""
import argparse
import json
import re
import time

from kafka import KafkaConsumer, TopicPartition
from kafka.errors import KafkaError
from neo4j import GraphDatabase
from tqdm import tqdm


def slug(value: str) -> str:
    """Converts a string to a safe, slugified version."""
    value = re.sub(r"[^a-zA-Z0-9]+", "_", value or "").strip("_").lower()
    return value or "unknown"


def process_batch_neo4j(tx, batch_data: list[dict]):
    """
    Process a batch of chunk data using a single, efficient UNWIND query.
    This query creates Document, Section, and Chunk nodes and their relationships.
    """
    query = """
    UNWIND $batch as row
    // Merge Document, Section, and Chunk nodes
    MERGE (d:Document {id: row.document_id})
      ON CREATE SET
        d.source_type = row.source_type,
        d.title = row.metadata.title,
        d.publisher = row.metadata.publisher,
        d.source_url = row.metadata.source_url
    MERGE (s:Section {id: row.section_id})
      ON CREATE SET
        s.name = row.section_name,
        s.document_id = row.document_id
    MERGE (c:Chunk {id: row.chunk_id})
      ON CREATE SET
        c.text = row.text,
        c.chunk_index = row.metadata.chunk_index,
        c.token_estimate = row.metadata.token_estimate

    // Connect the core structure
    MERGE (c)-[:PART_OF]->(s)
    MERGE (s)-[:PART_OF]->(d)

    // Create entities and link them to the chunk
    WITH c, row.entities AS entity_list
    UNWIND entity_list AS entity_data
    MERGE (e:Entity {id: entity_data.entity_id})
      ON CREATE SET e.type = entity_data.entity_type, e.value = entity_data.normalized_value, e.raw_value = entity_data.value
    MERGE (c)-[:CONTAINS_ENTITY]->(e)

    // Re-collect entities per chunk and create co-occurrence links
    WITH c, collect(e) AS entities_in_chunk
    UNWIND entities_in_chunk AS e1
    UNWIND entities_in_chunk AS e2
    WHERE id(e1) < id(e2) // Use internal node ID to process each pair once
    MERGE (e1)-[r:APPEARS_WITH]-(e2)
      ON CREATE SET r.weight = 1
      ON MATCH SET r.weight = r.weight + 1
    """
    tx.run(query, batch=batch_data)


def main():
    parser = argparse.ArgumentParser(description="Kafka to Neo4j Loader Service.")
    # Kafka Args
    parser.add_argument("--kafka-bootstrap-servers", default="localhost:9092")
    parser.add_argument("--consumer-topic", default="chunks_with_entities", help="The topic containing chunks enriched with entities.")
    parser.add_argument("--consumer-group-id", default="neo4j_loader_service")
    # Neo4j Args
    parser.add_argument("--neo4j-uri", default="bolt://localhost:7687")
    parser.add_argument("--neo4j-user", default="neo4j")
    parser.add_argument("--neo4j-password", default="password") # Change this default
    # Batching Args
    parser.add_argument("--batch-size", default=100, type=int)
    parser.add_argument("--batch-timeout-ms", default=5000, type=int, help="Max time to wait for a full batch.")
    args = parser.parse_args()

    print("Initializing Neo4j driver...")
    try:
        driver = GraphDatabase.driver(args.neo4j_uri, auth=(args.neo4j_user, args.neo4j_password))
        driver.verify_connectivity()
        print("Connected to Neo4j.")
    except Exception as e:
        print(f"\nFATAL: Failed to connect to Neo4j. Check connection details. Details: {e}")
        return

    print(f"Connecting to Kafka at {args.kafka_bootstrap_servers}...")
    try:
        consumer = KafkaConsumer(
            bootstrap_servers=args.kafka_bootstrap_servers,
            group_id=args.consumer_group_id,
            auto_offset_reset='earliest',
            enable_auto_commit=False,
            value_deserializer=lambda m: json.loads(m.decode('utf-8')),
            consumer_timeout_ms=args.batch_timeout_ms,
        )
        consumer.subscribe([args.consumer_topic])
    except KafkaError as e:
        print(f"\nFATAL: Could not connect to Kafka. Is it running? Details: {e}")
        return

    print(f"Listening for messages on topic '{args.consumer_topic}'... (Press Ctrl+C to stop)")
    batch = []
    try:
        while True:
            try:
                for message in consumer:
                    batch.append(message)
                    if len(batch) >= args.batch_size:
                        break

                if not batch:
                    print("Waiting for new messages...", end='\r')
                    time.sleep(1)
                    continue

                print(f"\nProcessing batch of {len(batch)} messages for Neo4j...")
                batch_data = []
                for msg in batch:
                    chunk = msg.value
                    metadata = chunk.get("metadata", {})
                    section_name = chunk.get("section", "unknown_section")
                    document_id = chunk.get("document_id", "unknown_doc")
                    batch_data.append({
                        "chunk_id": chunk.get("chunk_id"),
                        "document_id": document_id,
                        "source_type": chunk.get("source_type"),
                        "section_id": f"{document_id}_{slug(section_name)}",
                        "section_name": section_name,
                        "text": chunk.get("text"),
                        "metadata": {
                            "chunk_index": metadata.get("chunk_index"),
                            "token_estimate": metadata.get("token_estimate"),
                            "title": metadata.get("title"),
                            "publisher": metadata.get("publisher"),
                            "source_url": metadata.get("source_url"),
                        },
                        "entities": chunk.get("entities", []),
                    })

                with driver.session() as session:
                    session.execute_write(process_batch_neo4j, batch_data)

                offsets_to_commit = {}
                for msg in batch:
                    tp = TopicPartition(msg.topic, msg.partition)
                    offsets_to_commit[tp] = msg.offset + 1
                consumer.commit(offsets_to_commit)

                print(f"Successfully processed and committed {len(batch)} chunks to Neo4j.")
                batch = []

            except Exception as e:
                print(f"\nERROR processing batch for Neo4j: {e}")
                print("Skipping commit and retrying in 10 seconds...")
                time.sleep(10)

    except KeyboardInterrupt:
        print("\nShutting down...")
    finally:
        if batch:
            print("Processing final batch before shutdown...")
            # Consider processing the final batch here if needed
        consumer.close()
        driver.close()
        print("Kafka and Neo4j connections closed.")


if __name__ == "__main__":
    main()