import argparse
import hashlib
import json
import os
import re
from pathlib import Path 
from functools import lru_cache, partial

# Cấu hình model cấp dự án
from scraper.models import EMBEDDING_TOKENIZER

# LangChain is used for more semantic text splitting.
# Ensure it's installed: pip install langchain kafka-python
try:
    from transformers import AutoTokenizer
    # Sử dụng tokenizer tương ứng với model embedding để đếm token chính xác.
    _tokenizer = AutoTokenizer.from_pretrained(EMBEDDING_TOKENIZER)
except Exception as exc:
    print(f"WARNING: tokenizer unavailable, falling back to estimate: {exc}")
    _tokenizer = None

from langchain.text_splitter import RecursiveCharacterTextSplitter
from kafka import KafkaConsumer, KafkaProducer
from kafka.errors import KafkaError

from scraper.transform.text_normalization import normalize_text


def read_jsonl(path: Path) -> list[dict]:
    with path.open(encoding="utf-8-sig") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def write_jsonl(records: list[dict], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")


@lru_cache(maxsize=8192)
def token_estimate(text: str) -> int:
    """Estimates token count accurately using the model's tokenizer if available, else falls back to word count."""
    if not text:
        return 0
    if _tokenizer:
        return len(_tokenizer.encode(text, add_special_tokens=False))
    # Fallback to regex with a standard ~1.3 tokens per word multiplier
    return max(1, int(len(re.findall(r"\S+", text)) * 1.3))


def slug(value: str) -> str:
    value = re.sub(r"[^a-zA-Z0-9]+", "_", value or "").strip("_").lower()
    return value or "unknown"


def chunk_id(record: dict, index: int, text: str) -> str:
    digest = hashlib.sha1(text.encode("utf-8")).hexdigest()[:8]
    return f"{slug(record.get('document_id'))}__{slug(record.get('section'))}__{index:04d}__{digest}"


def recursive_chunk_text(text: str, chunk_size: int, overlap: int) -> list[str]:
    """Splits text into chunks using a recursive character-based strategy."""
    if not text:
        return []
    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=overlap,
        length_function=token_estimate,
        separators=["\n\n", "\n", ". ", ", ", " ", ""],
        keep_separator=True,
    )
    # We use normalize_text here to preserve newline characters, which are
    # critical separators for the RecursiveCharacterTextSplitter.
    return text_splitter.split_text(normalize_text(text))


def make_chunks(record: dict, text_splitter_func: callable) -> list[dict]:
    text_chunks = text_splitter_func(record.get("text", ""))
    if not text_chunks:
        return []

    chunks = []
    base_metadata = record.get("metadata", {}) or {}
    base_provenance = base_metadata.get("provenance", {}) or {}

    for index, text in enumerate(text_chunks, start=1):
        # Bắt đầu với một bản sao của provenance gốc và cập nhật nó
        provenance = base_provenance.copy()

        page_start = base_metadata.get("page_start") or base_metadata.get("page")
        source_url = base_metadata.get("source_url")
        source_locator = base_metadata.get("source_locator")
        if not source_locator and source_url and page_start:
            source_locator = f"{source_url}#page={page_start}"

        provenance.update(
            {
                "document_id": record.get("document_id"),
                "section": record.get("section") or base_metadata.get("section"),
                "chunk_index": index,
                "chunk_count": len(text_chunks),
                "source_locator": source_locator,  # Đảm bảo locator được cập nhật trong provenance
            }
        )

        # Xây dựng metadata cuối cùng cho chunk
        chunk_metadata = {
            # Kế thừa tất cả metadata từ section cha
            **base_metadata,
            # Thêm/ghi đè với dữ liệu của riêng chunk
            "chunk_index": index,
            "chunk_count": len(text_chunks),
            "token_estimate": token_estimate(text),
            "source_document_id": record.get("document_id"),
            "source_section": record.get("section") or base_metadata.get("section"),
            "source_locator": source_locator,
            "page": page_start,  # Giữ lại để tương thích
            # Chuyển tiếp một cách tường minh các topic quan trọng đã tìm thấy trong section
            "matched_important_topics": base_metadata.get("matched_important_topics", []),
            # Ghi đè với provenance đã được cập nhật, dành riêng cho chunk
            "provenance": provenance,
        }
        chunks.append(
            {
                "chunk_id": chunk_id(record, index, text),
                "document_id": record.get("document_id"),
                "source_type": record.get("source_type"),
                "section": record.get("section"),
                "text": text,
                "metadata": chunk_metadata,
            }
        )

    return chunks


def main() -> None:
    parser = argparse.ArgumentParser(description="A streaming service to chunk important sections from Kafka.")
    # Kafka arguments
    parser.add_argument("--kafka-bootstrap-servers", default="localhost:9092", help="Kafka bootstrap servers.")
    parser.add_argument("--consumer-topic", default="important_sections", help="Kafka topic to consume sections from.")
    parser.add_argument("--producer-topic", default="chunks_to_index", help="Kafka topic to produce chunks to.")
    parser.add_argument("--consumer-group-id", default="chunking_service", help="Kafka consumer group ID.")
    # Chunking arguments
    parser.add_argument(
        "--chunk-size",
        default=500,
        type=int,
        help="Target chunk size in embedding-model tokens for the recursive strategy.",
    )
    parser.add_argument(
        "--overlap",
        default=75,
        type=int,
        help="Chunk overlap in embedding-model tokens for the recursive strategy.",
    )
    args = parser.parse_args()

    # 1. Configure the chunking function
    print(f"Using 'recursive' chunking strategy with chunk size {args.chunk_size} and overlap {args.overlap}.")
    splitter_func = partial(recursive_chunk_text, chunk_size=args.chunk_size, overlap=args.overlap)

    # 2. Connect to Kafka
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
            value_serializer=lambda m: json.dumps(m).encode('utf-8')
        )
    except KafkaError as e:
        print(f"\nFATAL: Could not connect to Kafka. Is it running at {args.kafka_bootstrap_servers}?")
        print(f"Details: {e}")
        return

    # 3. Start the processing loop
    print(f"Listening for messages on topic '{args.consumer_topic}'... (Press Ctrl+C to stop)")
    try:
        for message in consumer:
            record = message.value
            document_id = record.get("document_id", "unknown_doc")
            print(f"  -> Processing section from document: {document_id}")
            chunks = make_chunks(record, splitter_func)
            for chunk in chunks:
                producer.send(args.producer_topic, value=chunk)
            producer.flush()
            print(f"     Produced {len(chunks)} chunks to topic '{args.producer_topic}'")
    except KeyboardInterrupt:
        print("\nShutting down...")
    finally:
        consumer.close()
        producer.close()
        print("Kafka connections closed.")


if __name__ == "__main__":
    main()
