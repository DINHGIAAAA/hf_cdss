import argparse
import os
import json
import re
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import pdfplumber
from kafka import KafkaProducer
from kafka.errors import KafkaError
from tqdm import tqdm

from scraper.transform.text_normalization import normalize_text


HEADING_RE = re.compile(
    r"^\s*("
    # Pattern 1: Numbered/lettered headings (e.g., "1.2 Title", "A. Title")
    r"((?:[A-Z]|\d+)(?:\.\d+)*\.?\s+.+)|"
    # Pattern 2: All-caps headings that the heuristic below might miss.
    # Loosened length from 9+ to 5+ and kept original punctuation.
    r"([A-Z][A-Z0-9 /,&:;()\-]{4,})"
    r")\s*$"
)


def clean_text(value: str) -> str:
    return normalize_text(value)


def document_id_from_path(path: Path) -> str:
    value = path.stem.lower()
    value = re.sub(r"[^a-z0-9]+", "_", value)
    return value.strip("_")


def load_registry(path: Path | None) -> dict[str, dict]:
    if path is None or not path.exists():
        return {}
    registry = json.loads(path.read_text(encoding="utf-8-sig"))
    rows = {}
    for source in registry.get("sources", []):
        target_path = str(source.get("target_path", "")).replace("\\", "/")
        rows[target_path] = source
        rows[Path(target_path).name] = source
        rows[document_id_from_path(Path(target_path))] = source
    return rows


def source_metadata(pdf_path: Path, registry: dict[str, dict]) -> dict:
    source = registry.get(pdf_path.name) or registry.get(document_id_from_path(pdf_path)) or {}
    if not source:
        normalized_path = pdf_path.as_posix()
        for target_path, row in registry.items():
            if "/" in target_path and normalized_path.endswith(target_path):
                source = row
                break
    citation = source.get("title") or pdf_path.stem
    publisher = source.get("publisher")
    if publisher:
        citation = f"{citation}. {publisher}."
    return {
        "source_id": source.get("source_id") or document_id_from_path(pdf_path),
        "source": "guideline_pdf",
        "source_type": "guideline",
        "source_url": source.get("url"),
        "publisher": publisher,
        "title": source.get("title") or pdf_path.stem,
        "citation": citation,
        "license_note": source.get("license_note"),
        "retrieved_at": source.get("downloaded_at") or source.get("retrieved_at"),
        "sha256": source.get("sha256"),
        "storage_uri": source.get("storage_uri"),
    }


def is_heading(line: str) -> bool:
    line = clean_text(line)
    # Loosen length constraints: min 4 for short words, max 200 for long titles
    if len(line) < 4 or len(line) > 200:
        return False

    # Heuristic: A line ending with a period is not a heading,
    # unless it's a numbered list item.
    if line.endswith(".") and not re.match(r"^\s*\d+(\.\d+)*", line):
        return False

    # Heuristic: A short line that is entirely uppercase is very likely a heading.
    # This is more robust than a complex regex for many common cases.
    if line.isupper() and len(line.split()) < 7:
        # Filter out captions that are often all-caps, e.g., "TABLE 1", "FIGURE A"
        if any(keyword in line for keyword in ["TABLE", "FIGURE", "CHART"]):
            return False
        return True

    # Finally, apply the main regex for more complex patterns.
    return bool(HEADING_RE.match(line))


def split_sections(pages: list[dict]) -> list[dict]:
    sections = []
    current = None

    for page in pages:
        lines = [clean_text(line) for line in page["text"].splitlines() if clean_text(line)]
        for line in lines:
            if is_heading(line):
                if current and clean_text(current["text"]):
                    current["text"] = clean_text(current["text"])
                    sections.append(current)
                current = {
                    "section": re.sub(r"^\d+(\.\d+)*\s+", "", line).upper(),
                    "text": "",
                    "page_start": page["page"],
                    "page_end": page["page"],
                }
                continue

            if current is None:
                current = {
                    "section": "FRONT MATTER",
                    "text": "",
                    "page_start": page["page"],
                    "page_end": page["page"],
                }

            current["text"] += line + "\n"
            current["page_end"] = page["page"]

    if current and clean_text(current["text"]):
        current["text"] = clean_text(current["text"])
        sections.append(current)

    return sections


def parse_pdf(
    pdf_path: Path,
    tables_dir: Path,
    extract_tables: bool,
    registry: dict[str, dict] | None = None,
    fast_parsing: bool = False,
) -> tuple[dict, list[dict], list[dict]]:
    provenance = source_metadata(pdf_path, registry or {})
    document_id = provenance["source_id"]
    guideline_topic = (registry or {}).get(pdf_path.name, {}).get("topic") or pdf_path.parent.name
    pages = []
    tables = []

    with pdfplumber.open(pdf_path) as pdf:
        for index, page in enumerate(pdf.pages, start=1):
            page_tables = []
            found_tables_data = []

            if extract_tables:
                # Define text-based strategy for fallback
                text_table_settings = {
                    "vertical_strategy": "text",
                    "horizontal_strategy": "text",
                    "snap_x_tolerance": 6,
                }
                # Try default (line-based) strategy first
                page_tables = page.find_tables()

                # If no tables found, try the slow text-based strategy unless fast parsing is enabled
                if not page_tables and not fast_parsing:
                    page_tables = page.find_tables(text_table_settings)
                
                found_tables_data = [t.extract() for t in page_tables]

            # Get bounding boxes of found tables to exclude their text from main content
            table_bboxes = [t.bbox for t in page_tables]

            def not_within_bboxes(obj):
                """Checks if an object's center is not within any of the given bounding boxes."""
                def obj_in_bbox(obj, bbox):
                    v_mid = (obj["top"] + obj["bottom"]) / 2
                    h_mid = (obj["x0"] + obj["x1"]) / 2
                    x0, top, x1, bottom = bbox
                    return (h_mid >= x0) and (h_mid < x1) and (v_mid >= top) and (v_mid < bottom)
                return not any(obj_in_bbox(obj, bbox) for bbox in table_bboxes)

            # Filter page to exclude tables, then extract text
            page_to_extract = page.filter(not_within_bboxes) if extract_tables and table_bboxes else page
            text = clean_text(page_to_extract.extract_text(layout=True) or "")
            pages.append({"page": index, "text": text})

            if extract_tables:
                for table_index, table in enumerate(found_tables_data or [], start=1):
                    if not table:
                        continue
                    table_record = {
                        "document_id": document_id,
                        "source_type": "guideline",
                        "page": index,
                        "table_index": table_index,
                        "rows": table,
                        "metadata": {
                            **provenance,
                            "guideline_topic": guideline_topic,
                            "source_file": str(pdf_path),
                            "page": index,
                            "section": f"TABLE {table_index}",
                            "provenance": {
                                "source_id": provenance["source_id"],
                                "source_url": provenance.get("source_url"),
                                "page": index,
                                "table_index": table_index,
                            },
                        },
                    }
                    tables.append(table_record)

    document = {
        "document_id": document_id,
        "source_type": "guideline",
        "text": clean_text("\n\n".join(page["text"] for page in pages)),
        "metadata": {
            **provenance,
            "guideline_topic": guideline_topic,
            "source_file": str(pdf_path),
            "page_count": len(pages),
            "provenance": {
                "source_id": provenance["source_id"],
                "source_url": provenance.get("source_url"),
                "page_start": 1 if pages else None,
                "page_end": len(pages) if pages else None,
            },
        },
    }

    sections = []
    for section in split_sections(pages):
        sections.append(
            {
                "document_id": document_id,
                "source_type": "guideline",
                "section": section["section"],
                "text": section["text"],
                "metadata": {
                    **provenance,
                    "guideline_topic": guideline_topic,
                    "source_file": str(pdf_path),
                    "page_start": section["page_start"],
                    "page_end": section["page_end"],
                    "page": section["page_start"],
                    "provenance": {
                        "source_id": provenance["source_id"],
                        "source_url": provenance.get("source_url"),
                        "section": section["section"],
                        "page_start": section["page_start"],
                        "page_end": section["page_end"],
                    },
                },
            }
        )

    if tables:
        tables_dir.mkdir(parents=True, exist_ok=True)
        table_output = tables_dir / f"{document_id}_tables.jsonl"
        with table_output.open("w", encoding="utf-8", newline="\n") as handle:
            for table in tables:
                handle.write(json.dumps(table, ensure_ascii=False) + "\n")

    return document, sections, tables


def write_jsonl(records: list[dict], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="\n") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")


def parse_pdf_job(args: tuple[Path, Path, bool, dict, bool]) -> tuple[dict, list[dict], list[dict]]:
    pdf_path = args[0]
    with pdf_path.open("rb") as handle:
        if handle.read(4) != b"%PDF":
            print(f"Skipping non-PDF file: {pdf_path}")
            return {}, [], []
    return parse_pdf(*args)


def main() -> None:
    parser = argparse.ArgumentParser(description="Parse guideline PDFs and produce documents and sections to Kafka topics.")
    parser.add_argument("--input-dir", default="raw/guidelines", type=Path)
    parser.add_argument("--registry", default="sources/sources.example.json", type=Path)
    parser.add_argument("--tables-dir", default="processed/tables", type=Path)
    parser.add_argument("--extract-tables", action="store_true")
    parser.add_argument("--fast-parsing", action="store_true", help="Use faster, less accurate parsing settings (e.g., disable text-based table finding).")
    # Kafka arguments
    parser.add_argument("--kafka-bootstrap-servers", default="localhost:9092", help="Kafka bootstrap servers.")
    parser.add_argument("--sections-topic", default="sections_parsed", help="Kafka topic to produce parsed sections to.")
    parser.add_argument("--documents-topic", default="guideline_documents", help="Kafka topic to produce document metadata to.")
    parser.add_argument(
        "--workers",
        default=max((os.cpu_count() or 2) - 1, 1),
        type=int,
        help="Number of PDFs to parse in parallel. Use 1 for deterministic single-process parsing.",
    )
    args = parser.parse_args()

    print(f"Connecting to Kafka at {args.kafka_bootstrap_servers}...")
    try:
        producer = KafkaProducer(
            bootstrap_servers=args.kafka_bootstrap_servers,
            value_serializer=lambda m: json.dumps(m, ensure_ascii=False).encode('utf-8')
        )
    except KafkaError as e:
        print(f"\nFATAL: Could not connect to Kafka. Is it running? Details: {e}")
        return

    registry = load_registry(args.registry)
    pdf_paths = sorted(args.input_dir.glob("*/*.pdf"))
    jobs = [(pdf_path, args.tables_dir, args.extract_tables, registry, args.fast_parsing) for pdf_path in pdf_paths]

    results = []
    doc_count, sec_count, table_count = 0, 0, 0
    try:
        if args.workers == 1 or len(jobs) <= 1:
            print(f"Parsing {len(jobs)} PDFs sequentially...")
            results = [parse_pdf_job(job) for job in tqdm(jobs)]
        else:
            with ProcessPoolExecutor(max_workers=args.workers) as executor:
                print(f"Parsing {len(jobs)} PDFs with {args.workers} workers...")
                results = list(tqdm(executor.map(parse_pdf_job, jobs), total=len(jobs)))

        print("\nProducing results to Kafka...")
        for document, pdf_sections, tables in tqdm(results, desc="Producing to Kafka"):
            if not document:
                continue
            producer.send(args.documents_topic, value=document)
            doc_count += 1
            for section in pdf_sections:
                producer.send(args.sections_topic, value=section)
            sec_count += len(pdf_sections)
            table_count += len(tables)
        
        print("Flushing Kafka producer...")
        producer.flush()

    except KeyboardInterrupt:
        print("\nShutting down...")
    finally:
        if 'producer' in locals():
            producer.close()
            print("Kafka producer closed.")

    print("\n--- Processing Summary ---")
    print(f"Total PDFs processed: {len(jobs)}")
    print(f"Total documents produced to '{args.documents_topic}': {doc_count}")
    print(f"Total sections produced to '{args.sections_topic}': {sec_count}")
    print(f"Total tables saved to disk: {table_count}")


if __name__ == "__main__":
    main()
