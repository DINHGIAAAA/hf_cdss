from scraper.io.jsonl import read_jsonl, write_jsonl
import argparse
import os
import json
import re
import shutil
import tempfile
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

from tqdm import tqdm

from scraper.transform.opendataloader_extract import (
    convert_pdfs,
    extract_with_opendataloader,
    opendataloader_available,
)
from scraper.transform.table_sections import build_table_section_records
from scraper.transform.text_normalization import append_flow_line, normalize_text, repair_pdf_flow_text

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

IGNORED_SECTION_TITLES = {
    "CONTENTS", "TABLE OF CONTENTS", "REFERENCES", "BIBLIOGRAPHY",
    "CONTRIBUTORS", "DISCLOSURES", "APPENDIX", "INDEX", "PEER REVIEW"
}

def split_sections(pages: list[dict]) -> list[dict]:
    sections = []
    current = None

    for page in pages:
        lines = [clean_text(line) for line in page["text"].splitlines() if clean_text(line)]
        for line in lines:
            forced_heading = line.startswith("# ")
            if forced_heading:
                line = line[2:].strip()

            if forced_heading or is_heading(line):
                if current and clean_text(current["text"]):
                    current["text"] = repair_pdf_flow_text(current["text"])
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

            current["text"] = append_flow_line(current["text"], line)
            current["page_end"] = page["page"]

    if current and clean_text(current["text"]):
        current["text"] = repair_pdf_flow_text(current["text"])
        sections.append(current)

    # Filter out low-value sections like table of contents, references, etc.
    filtered_sections = []
    for section in sections:
        section_title = section.get("section", "").upper()
        # Check if any part of the section title matches the ignored keywords
        if any(ignored in section_title for ignored in IGNORED_SECTION_TITLES):
            print(f"  -> Filtering out low-value section: {section_title}")
            continue
        filtered_sections.append(section)

    return filtered_sections

def parse_pdf_with_pdfplumber(
    pdf_path: Path,
    fast_parsing: bool = False,
) -> tuple[list[dict], list[dict]]:
    import pdfplumber

    pages = []
    tables = []

    with pdfplumber.open(pdf_path) as pdf:
        for index, page in enumerate(pdf.pages, start=1):
            text_table_settings = {
                "vertical_strategy": "text",
                "horizontal_strategy": "text",
                "snap_x_tolerance": 6,
            }
            page_tables = page.find_tables()

            if not page_tables and not fast_parsing:
                page_tables = page.find_tables(text_table_settings)

            found_tables_data = [t.extract() for t in page_tables]
            table_bboxes = [t.bbox for t in page_tables]

            def not_within_bboxes(obj):
                def obj_in_bbox(obj, bbox):
                    v_mid = (obj["top"] + obj["bottom"]) / 2
                    h_mid = (obj["x0"] + obj["x1"]) / 2
                    x0, top, x1, bottom = bbox
                    return (h_mid >= x0) and (h_mid < x1) and (v_mid >= top) and (v_mid < bottom)

                return not any(obj_in_bbox(obj, bbox) for bbox in table_bboxes)

            page_to_extract = page.filter(not_within_bboxes) if table_bboxes else page
            text = repair_pdf_flow_text(page_to_extract.extract_text(x_tolerance=2, y_tolerance=2) or "")
            pages.append({"page": index, "text": text})

            for table_index, table in enumerate(found_tables_data or [], start=1):
                if not table:
                    continue
                tables.append(
                    {
                        "page": index,
                        "table_index": table_index,
                        "rows": table,
                    }
                )

    return pages, tables

def parse_pdf(
    pdf_path: Path,
    tables_dir: Path,
    registry: dict[str, dict] | None = None,
    fast_parsing: bool = False,
    odl_cache_dir: Path | None = None,
    use_opendataloader: bool = True,
) -> tuple[dict, list[dict], list[dict]]:
    provenance = source_metadata(pdf_path, registry or {})
    document_id = provenance["source_id"]
    guideline_topic = (registry or {}).get(pdf_path.name, {}).get("topic") or pdf_path.parent.name
    pages: list[dict] = []
    raw_tables: list[dict] = []
    parser_engine = "pdfplumber"

    if use_opendataloader and opendataloader_available():
        try:
            pages, raw_tables = extract_with_opendataloader(
                pdf_path,
                cache_dir=odl_cache_dir,
                quiet=True,
            )
            parser_engine = "opendataloader"
        except Exception as exc:
            print(f"  -> OpenDataLoader failed for {pdf_path.name}, falling back to pdfplumber: {exc}")

    if not pages:
        pages, raw_tables = parse_pdf_with_pdfplumber(
            pdf_path,
            fast_parsing=fast_parsing,
        )

    tables, table_sections = build_table_section_records(
        raw_tables,
        document_id=document_id,
        provenance=provenance,
        guideline_topic=guideline_topic,
        source_file=str(pdf_path),
    )

    document = {
        "document_id": document_id,
        "source_type": "guideline",
        "text": clean_text("\n\n".join(page["text"] for page in pages)),
        "metadata": {
            **provenance,
            "guideline_topic": guideline_topic,
            "source_file": str(pdf_path),
            "page_count": len(pages),
            "parser_engine": parser_engine,
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

    sections.extend(table_sections)

    if tables:
        tables_dir.mkdir(parents=True, exist_ok=True)
        table_output = tables_dir / f"{document_id}_tables.jsonl"
        with table_output.open("w", encoding="utf-8", newline="\n") as handle:
            for table in tables:
                handle.write(json.dumps(table, ensure_ascii=False) + "\n")

    return document, sections, tables

def parse_pdf_job(args: tuple[Path, Path, dict, bool, Path | None, bool]) -> tuple[dict, list[dict], list[dict]]:
    pdf_path = args[0]
    with pdf_path.open("rb") as handle:
        if handle.read(4) != b"%PDF":
            print(f"Skipping non-PDF file: {pdf_path}")
            return {}, [], []
    return parse_pdf(*args)

def main() -> None:
    from scraper.paths import guidelines_dir

    parser = argparse.ArgumentParser(description="Parse guideline PDFs and produce documents and sections.")
    parser.add_argument(
        "--input-dir",
        default=None,
        type=Path,
        help="Guideline PDF root (default: HF_CDSS_RAW_ROOT/guidelines).",
    )
    parser.add_argument("--registry", default="sources/sources.example.json", type=Path)
    parser.add_argument("--tables-dir", default="processed/tables", type=Path)
    parser.add_argument("--fast-parsing", action="store_true", help="Use faster, less accurate parsing settings (e.g., disable text-based table finding).")
    parser.add_argument(
        "--pdf-parser",
        default="opendataloader",
        choices=["opendataloader", "pdfplumber"],
        help="PDF extraction engine. OpenDataLoader requires Java 11+.",
    )
    parser.add_argument("--documents-output", default="processed/documents/guideline_documents.jsonl", type=Path)
    parser.add_argument("--sections-output", default="processed/sections/guideline_sections.jsonl", type=Path)
    parser.add_argument(
        "--workers",
        default=max((os.cpu_count() or 2) - 1, 1),
        type=int,
        help="Number of PDFs to parse in parallel. Use 1 for deterministic single-process parsing.",
    )
    args = parser.parse_args()
    input_dir = args.input_dir or guidelines_dir()

    registry = load_registry(args.registry)
    pdf_paths = sorted(input_dir.glob("*/*.pdf"))
    use_opendataloader = args.pdf_parser == "opendataloader"
    odl_cache_dir: Path | None = None

    if use_opendataloader and opendataloader_available() and pdf_paths:
        odl_cache_dir = Path(tempfile.mkdtemp(prefix="odl_batch_"))
        print(f"Converting {len(pdf_paths)} PDFs with OpenDataLoader (batch JVM)...")
        convert_pdfs(pdf_paths, odl_cache_dir, quiet=True)
    elif use_opendataloader and not opendataloader_available():
        print("OpenDataLoader unavailable (Java or package missing); using pdfplumber fallback.")
        use_opendataloader = False

    jobs = [
        (
            pdf_path,
            args.tables_dir,
            registry,
            args.fast_parsing,
            odl_cache_dir,
            use_opendataloader,
        )
        for pdf_path in pdf_paths
    ]

    documents: list[dict] = []
    sections: list[dict] = []
    doc_count, sec_count, table_count = 0, 0, 0
    try:
        if args.workers == 1 or len(jobs) <= 1:
            print(f"Parsing {len(jobs)} PDFs sequentially...")
            results = [parse_pdf_job(job) for job in tqdm(jobs)]
        else:
            with ProcessPoolExecutor(max_workers=args.workers) as executor:
                print(f"Parsing {len(jobs)} PDFs with {args.workers} workers...")
                results = list(tqdm(executor.map(parse_pdf_job, jobs), total=len(jobs)))

        for document, pdf_sections, tables in results:
            if not document:
                continue
            documents.append(document)
            sections.extend(pdf_sections)
            if tables:
                args.tables_dir.mkdir(parents=True, exist_ok=True)
                table_path = args.tables_dir / f"{document['document_id']}_tables.jsonl"
                write_jsonl(tables, table_path)
                table_count += len(tables)

        write_jsonl(documents, args.documents_output)
        write_jsonl(sections, args.sections_output)
        doc_count = len(documents)
        sec_count = len(sections)
        print(f"\nWrote {doc_count} documents to '{args.documents_output}'")
        print(f"Wrote {sec_count} sections to '{args.sections_output}'")

    except KeyboardInterrupt:
        print("\nShutting down...")
    finally:
        if odl_cache_dir is not None:
            shutil.rmtree(odl_cache_dir, ignore_errors=True)

    print("\n--- Processing Summary ---")
    print(f"Total PDFs processed: {len(jobs)}")
    print(f"Total documents written: {doc_count}")
    print(f"Total sections written: {sec_count}")
    print(f"Total tables saved to disk: {table_count}")

if __name__ == "__main__":
    main()
