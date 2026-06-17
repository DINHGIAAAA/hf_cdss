"""A streaming service to load chunks from Kafka into ChromaDB efficiently.

This service consumes messages from a Kafka topic, batches them, generates
embeddings, and upserts them into a ChromaDB collection.

Key features:
- Batch processing for efficient embedding and database writes.
- Manual offset management for at-least-once delivery guarantee.
- Configurable via command-line arguments.
- Graceful shutdown.
"""
import argparse
import json
import re
import time

import chromadb
from kafka import KafkaConsumer, TopicPartition
from kafka.errors import KafkaError
from langchain_ollama.embeddings import OllamaEmbeddings
from tqdm import tqdm

# Cấu hình model cấp dự án
from scraper.models import (
    CHROMA_COLLECTION,
    CHROMA_INDEX_VERSION,
    EMBEDDING_DIMENSIONS,
    EMBEDDING_MODEL,
    EMBEDDING_PROVIDER,
)


def slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_") or "default"


def default_collection_name() -> str:
    provider = slug(EMBEDDING_PROVIDER)
    model = slug(EMBEDDING_MODEL)
    return f"{CHROMA_COLLECTION}_{CHROMA_INDEX_VERSION}_{provider}_{model}_{EMBEDDING_DIMENSIONS}"


def searchable_text(chunk: dict) -> str:
    metadata = chunk.get("metadata", {}) or {}
    return " ".join(
        [
            chunk.get("document_id", ""),
            chunk.get("source_type", ""),
            chunk.get("section", ""),
            chunk.get("text", ""),
            " ".join(str(value) for value in metadata.values() if isinstance(value, str)),
        ]
    )


def process_batch(batch: list, collection: chromadb.Collection, embeddings_model: OllamaEmbeddings):
    """
    Process a batch of messages: generate embeddings and upsert to ChromaDB.
    """
    if not batch:
        return

    # 1. Prepare data for ChromaDB and embedding model
    ids = [msg.value["chunk_id"] for msg in batch]
    documents = [msg.value["text"] for msg in batch]
    searchable_documents = [searchable_text(msg.value) for msg in batch]

    # 2. Sanitize metadata for ChromaDB (only scalar values allowed)
    metadatas = []
    for msg in batch:
        chunk = msg.value
        original_meta = chunk.get("metadata", {}) or {}
        full_metadata = dict(original_meta)
        if chunk.get("entities"):
            full_metadata["entities"] = chunk.get("entities")

        sanitized_meta = {
            "document_id": chunk.get("document_id", ""),
            "source_type": chunk.get("source_type", ""),
            "section": chunk.get("section") or "",
            "metadata_json": json.dumps(full_metadata, ensure_ascii=False),
        }

        for key, value in original_meta.items():
            if key in {"document_id", "source_type", "section", "metadata_json"}:
                continue
            if isinstance(value, (str, int, float, bool)):
                sanitized_meta[key] = value

        metadatas.append(sanitized_meta)

    # 3. Generate embeddings for the entire batch at once
    embeddings = embeddings_model.embed_documents(searchable_documents)

    # 4. Upsert the batch to ChromaDB
    # `upsert` is idempotent: it adds new documents or updates existing ones.
    collection.upsert(
        ids=ids,
        embeddings=embeddings,
        metadatas=metadatas,
        documents=documents
    )


def main():
    parser = argparse.ArgumentParser(description="Kafka to ChromaDB Loader Service.")
    # Kafka Args
    parser.add_argument("--kafka-bootstrap-servers", default="localhost:9092")
    parser.add_argument("--consumer-topic", default="chunks_with_entities", help="The topic containing chunks to be indexed.")
    parser.add_argument("--consumer-group-id", default="chromadb_loader_service")
    # ChromaDB Args
    parser.add_argument("--chroma-host", default="localhost")
    parser.add_argument("--chroma-port", default=8001, type=int)
    parser.add_argument("--chroma-collection", default=default_collection_name())
    # Embedding Model Args
    parser.add_argument("--embedding-model", default=EMBEDDING_MODEL, help=f"Tên của model embedding để sử dụng trong Ollama. Mặc định: {EMBEDDING_MODEL}")
    parser.add_argument("--embedding-base-url", default="http://localhost:11434")
    # Batching Args
    parser.add_argument("--batch-size", default=100, type=int)
    parser.add_argument("--batch-timeout-ms", default=5000, type=int, help="Max time to wait for a full batch.")
    args = parser.parse_args()

    # 1. Initialize expensive components
    print("Initializing components...")
    try:
        embeddings_model = OllamaEmbeddings(model=args.embedding_model, base_url=args.embedding_base_url)
        chroma_client = chromadb.HttpClient(host=args.chroma_host, port=args.chroma_port)
        collection = chroma_client.get_or_create_collection(
            name=args.chroma_collection,
            configuration={"hnsw": {"space": "cosine"}},
        )
        print(f"Connected to ChromaDB. Collection '{args.chroma_collection}' has {collection.count()} documents.")
    except Exception as e:
        print(f"\nFATAL: Failed to initialize components. Check connections to Ollama/ChromaDB.")
        print(f"Details: {e}")
        return

    # 2. Connect to Kafka
    print(f"Connecting to Kafka at {args.kafka_bootstrap_servers}...")
    try:
        # enable_auto_commit=False is crucial for manual offset management
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
        print(f"\nFATAL: Could not connect to Kafka. Is it running?")
        print(f"Details: {e}")
        return

    # 3. Start the main processing loop
    print(f"Listening for messages on topic '{args.consumer_topic}'... (Press Ctrl+C to stop)")
    batch = []
    try:
        while True:
            try:
                for message in consumer:
                    batch.append(message)
                    if len(batch) >= args.batch_size:
                        break  # Process the full batch

                if not batch:
                    # No messages received in the last `consumer_timeout_ms`
                    print("Waiting for new messages...", end='\r')
                    time.sleep(1)
                    continue

                print(f"\nProcessing batch of {len(batch)} messages...")
                with tqdm(total=len(batch)) as pbar:
                    process_batch(batch, collection, embeddings_model)
                    pbar.update(len(batch))

                # IMPORTANT: Commit offsets only after the batch is successfully processed
                offsets_to_commit = {}
                for msg in batch:
                    tp = TopicPartition(msg.topic, msg.partition)
                    offsets_to_commit[tp] = msg.offset + 1
                consumer.commit(offsets_to_commit)

                print(f"Successfully processed and committed {len(batch)} chunks. Collection now has {collection.count()} documents.")
                batch = []

            except Exception as e:
                print(f"\nERROR processing batch: {e}")
                print("Skipping commit and retrying in 10 seconds...")
                time.sleep(10)

    except KeyboardInterrupt:
        print("\nShutting down...")
    finally:
        # Process any remaining messages before exiting
        if batch:
            print(f"\nProcessing final batch of {len(batch)} messages before shutdown...")
            process_batch(batch, collection, embeddings_model)
            consumer.commit()
            print("Final batch processed.")

        consumer.close()
        print("Kafka consumer closed.")


if __name__ == "__main__":
    main()
