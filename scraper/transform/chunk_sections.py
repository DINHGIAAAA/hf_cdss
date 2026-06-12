import argparse
import hashlib
import json
import re
from pathlib import Path

from scraper.transform.text_normalization import normalize_inline_text


def read_jsonl(path: Path) -> list[dict]:
    with path.open(encoding="utf-8-sig") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def write_jsonl(records: list[dict], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")


def token_estimate(text: str) -> int:
    return max(1, len(re.findall(r"\S+", text)))


def slug(value: str) -> str:
    value = re.sub(r"[^a-zA-Z0-9]+", "_", value or "").strip("_").lower()
    return value or "unknown"


def chunk_id(record: dict, index: int, text: str) -> str:
    digest = hashlib.sha1(text.encode("utf-8")).hexdigest()[:8]
    return f"{slug(record.get('document_id'))}__{slug(record.get('section'))}__{index:04d}__{digest}"


def split_words_with_overlap(text: str, chunk_size: int, overlap: int) -> list[str]:
    words = re.findall(r"\S+", normalize_inline_text(text))
    if not words:
        return []

    chunks = []
    start = 0
    step = max(chunk_size - overlap, 1)
    while start < len(words):
        end = min(start + chunk_size, len(words))
        chunks.append(" ".join(words[start:end]))
        if end == len(words):
            break
        start += step
    return chunks


def make_chunks(record: dict, chunk_size: int, overlap: int) -> list[dict]:
    text_chunks = split_words_with_overlap(record.get("text", ""), chunk_size, overlap)
    chunks = []

    for index, text in enumerate(text_chunks, start=1):
        metadata = dict(record.get("metadata") or {})
        provenance = dict(metadata.get("provenance") or {})
        page_start = metadata.get("page_start") or metadata.get("page")
        page_end = metadata.get("page_end") or metadata.get("page")
        source_id = metadata.get("source_id") or record.get("document_id")
        source_section = record.get("section") or metadata.get("section")
        provenance.update(
            {
                "source_id": source_id,
                "source_url": metadata.get("source_url"),
                "document_id": record.get("document_id"),
                "section": source_section,
                "page_start": page_start,
                "page_end": page_end,
                "chunk_index": index,
                "chunk_count": len(text_chunks),
            }
        )
        metadata.update(
            {
                "chunk_index": index,
                "chunk_count": len(text_chunks),
                "token_estimate": token_estimate(text),
                "source_document_id": record.get("document_id"),
                "source_section": source_section,
                "source_id": source_id,
                "source_url": metadata.get("source_url"),
                "publisher": metadata.get("publisher"),
                "citation": metadata.get("citation"),
                "title": metadata.get("title"),
                "retrieved_at": metadata.get("retrieved_at"),
                "published_date": metadata.get("published_date"),
                "page": page_start,
                "page_start": page_start,
                "page_end": page_end,
                "provenance": provenance,
            }
        )
        chunks.append(
            {
                "chunk_id": chunk_id(record, index, text),
                "document_id": record.get("document_id"),
                "source_type": record.get("source_type"),
                "section": record.get("section"),
                "text": text,
                "metadata": metadata,
            }
        )

    return chunks


def main() -> None:
    parser = argparse.ArgumentParser(description="Chunk important sections for extraction and retrieval.")
    parser.add_argument("--input", default="processed/sections/important_sections.jsonl", type=Path)
    parser.add_argument("--output", default="artifacts/chunks/chunks.jsonl", type=Path)
    parser.add_argument("--chunk-size", default=900, type=int)
    parser.add_argument("--overlap", default=120, type=int)
    args = parser.parse_args()

    chunks = []
    for record in read_jsonl(args.input):
        chunks.extend(make_chunks(record, args.chunk_size, args.overlap))

    write_jsonl(chunks, args.output)
    print(f"Wrote {len(chunks)} chunks to {args.output}")


if __name__ == "__main__":
    main()
