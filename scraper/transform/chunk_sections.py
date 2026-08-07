import argparse
import hashlib
from functools import lru_cache
from pathlib import Path

from scraper.io.jsonl import read_jsonl, write_jsonl

# Cấu hình model cấp dự án
from scraper.models import EMBEDDING_TOKENIZER

try:
    from transformers import AutoTokenizer

    _tokenizer = AutoTokenizer.from_pretrained(EMBEDDING_TOKENIZER)
    # Counting-only: do not enforce BGE model_max_length (8192) or transformers
    # warns "Token indices sequence length is longer than ..." on long sections.
    _tokenizer.model_max_length = 10**9
except Exception as exc:
    print(f"WARNING: tokenizer unavailable, falling back to estimate: {exc}")
    _tokenizer = None

from langchain_text_splitters import RecursiveCharacterTextSplitter

from scraper.kg.identifiers import section_id_for_record, slug
from scraper.semantic import config
from scraper.semantic.chunking import structure_semantic_chunk_text
from scraper.transform.table_sections import is_extracted_table_section
from scraper.transform.text_normalization import repair_pdf_flow_text


@lru_cache(maxsize=16384)
def token_estimate(text: str) -> int:
    """Estimate token count for a text string.

    Uses BGE-M3 tokenizer when available (most accurate for embedding model),
    falls back to optimized word-based estimation.
    """
    if not text:
        return 0
    if _tokenizer:
        return len(
            _tokenizer.encode(
                text,
                add_special_tokens=False,
                truncation=False,
            )
        )
    # Optimized fallback: avoid regex overhead
    return max(1, int(len(text.split()) * 1.3))


def chunk_id(record: dict, index: int, text: str) -> str:
    digest = hashlib.sha1(text.encode("utf-8")).hexdigest()[:8]
    return f"{slug(record.get('document_id'))}__{slug(record.get('section'))}__{index:04d}__{digest}"


def recursive_chunk_text(text: str, chunk_size: int, overlap: int) -> list[str]:
    """Splits text using a recursive character-based strategy."""
    if not text:
        return []
    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=overlap,
        length_function=token_estimate,
        separators=["\n\n", "\n", ". ", ", ", " ", ""],
        keep_separator=True,
    )
    return text_splitter.split_text(repair_pdf_flow_text(text))


def should_use_semantic_chunking(record: dict, text: str) -> bool:
    if not config.SEMANTIC_CHUNK_ENABLED:
        return False
    if record.get("source_type") not in {"guideline", "drug_label"}:
        return False
    if is_extracted_table_section(record):
        return False
    if token_estimate(text) < config.SEMANTIC_CHUNK_MIN_SECTION_TOKENS:
        return False
    return True


def chunk_section_text(
    text: str,
    chunk_size: int,
    overlap: int,
    *,
    record: dict | None = None,
    use_semantic: bool | None = None,
) -> list[str]:
    """Structure-aware chunking with optional semantic breakpoints for long guidelines."""
    cleaned = (text or "").strip()
    if not cleaned:
        return []

    if token_estimate(cleaned) <= chunk_size:
        return [cleaned]

    semantic = use_semantic
    if semantic is None and record is not None:
        semantic = should_use_semantic_chunking(record, cleaned)
    if semantic is None:
        semantic = True

    try:
        chunks = structure_semantic_chunk_text(
            cleaned,
            chunk_size=chunk_size,
            overlap=overlap,
            token_estimate=token_estimate,
            use_semantic=semantic,
        )
        if chunks:
            return chunks
    except Exception as exc:
        print(f"WARNING: semantic chunking failed, using character split: {exc}")
    return recursive_chunk_text(cleaned, chunk_size, overlap)


def make_chunks(record: dict, chunk_size: int, overlap: int) -> list[dict]:
    text_chunks = chunk_section_text(
        record.get("text", ""),
        chunk_size,
        overlap,
        record=record,
    )
    if not text_chunks:
        return []

    chunks = []
    base_metadata = record.get("metadata", {}) or {}
    base_provenance = base_metadata.get("provenance", {}) or {}
    parent_section_id = record.get("section_id") or base_metadata.get("section_id") or section_id_for_record(record)
    chunk_strategy = "semantic" if should_use_semantic_chunking(record, record.get("text", "")) else "structure"

    for index, text in enumerate(text_chunks, start=1):
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
                "section_id": parent_section_id,
                "chunk_index": index,
                "chunk_count": len(text_chunks),
                "source_locator": source_locator,
            }
        )

        prev_chunk_id = chunks[-1]["chunk_id"] if chunks else None
        chunk_metadata = {
            **base_metadata,
            "section_id": parent_section_id,
            "chunk_index": index,
            "chunk_count": len(text_chunks),
            "chunk_strategy": chunk_strategy,
            "token_estimate": token_estimate(text),
            "source_document_id": record.get("document_id"),
            "source_section": record.get("section") or base_metadata.get("section"),
            "source_locator": source_locator,
            "page": page_start,
            "matched_important_topics": base_metadata.get("matched_important_topics", []),
            "overlap_with_prev": index > 1,
            "prev_chunk_id": prev_chunk_id,
            "provenance": provenance,
        }
        current_chunk_id = chunk_id(record, index, text)
        chunks.append(
            {
                "chunk_id": current_chunk_id,
                "document_id": record.get("document_id"),
                "source_type": record.get("source_type"),
                "section": record.get("section"),
                "section_id": parent_section_id,
                "text": text,
                "metadata": chunk_metadata,
            }
        )

    return chunks


def dedupe_chunks(chunks: list[dict]) -> list[dict]:
    seen: set[str] = set()
    unique: list[dict] = []
    for chunk in chunks:
        chunk_key = chunk.get("chunk_id")
        if chunk_key in seen:
            continue
        seen.add(chunk_key)
        unique.append(chunk)
    return unique


def main() -> None:
    parser = argparse.ArgumentParser(description="Chunk important sections into retrieval-ready artifacts.")
    parser.add_argument("--input", default="processed/sections/important_sections.jsonl", type=Path)
    parser.add_argument("--output", default="artifacts/chunks/chunks.jsonl", type=Path)
    parser.add_argument(
        "--chunk-size",
        default=config.DEFAULT_CHUNK_SIZE,
        type=int,
        help="Target chunk size in embedding-model tokens for the recursive strategy.",
    )
    parser.add_argument(
        "--overlap",
        default=config.DEFAULT_CHUNK_OVERLAP,
        type=int,
        help="Chunk overlap in embedding-model tokens.",
    )
    args = parser.parse_args()

    def log(message: str) -> None:
        # Airflow captures pipes; always flush so progress is visible during long embeds.
        print(message, flush=True)

    log(
        "Chunking with conditional semantic strategy "
        f"(size={args.chunk_size}, overlap={args.overlap}, "
        f"semantic_min_tokens={config.SEMANTIC_CHUNK_MIN_SECTION_TOKENS})."
    )

    log(f"Loading sections from {args.input}...")
    records = list(read_jsonl(args.input))
    total = len(records)
    log(f"Chunking {total} important sections (progress every 50)...")

    chunks: list[dict] = []
    semantic_sections = 0
    for index, record in enumerate(records, start=1):
        use_semantic = should_use_semantic_chunking(record, record.get("text", ""))
        if use_semantic:
            semantic_sections += 1
        chunks.extend(make_chunks(record, args.chunk_size, args.overlap))
        if index == 1 or index % 50 == 0 or index == total:
            log(
                f"Chunk progress: {index}/{total} sections, "
                f"{len(chunks)} chunks so far, "
                f"{semantic_sections} semantic-eligible"
            )
    chunks = dedupe_chunks(chunks)

    from scraper.semantic.dedup import dedupe_chunks as dedupe_chunks_by_embedding

    before = len(chunks)
    log(f"Embedding-dedup starting for {before} chunks (can take a while on Ollama)...")
    chunks = dedupe_chunks_by_embedding(chunks)
    log(
        f"Deduped chunks: {before} -> {len(chunks)} "
        f"(embedding_dedup={'on' if config.EMBEDDING_DEDUP_ENABLED else 'minhash-only'})."
    )
    write_jsonl(chunks, args.output)
    log(f"Wrote {len(chunks)} chunks to {args.output} ({semantic_sections} sections used semantic breakpoints).")


if __name__ == "__main__":
    main()
