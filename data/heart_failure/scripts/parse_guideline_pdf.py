import argparse
import os
import json
import re
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import pdfplumber


HEADING_RE = re.compile(
    r"^("
    r"(\d+(\.\d+){0,4}\s+[\w(])|"
    r"([A-Z][A-Z0-9 /,&:;()\-]{8,})"
    r")"
)


def clean_text(value: str) -> str:
    value = (value or "").replace("\xa0", " ")
    value = re.sub(r"[ \t]+", " ", value)
    value = re.sub(r"\n{3,}", "\n\n", value)
    return value.strip()


def document_id_from_path(path: Path) -> str:
    value = path.stem.lower()
    value = re.sub(r"[^a-z0-9]+", "_", value)
    return value.strip("_")


def is_heading(line: str) -> bool:
    line = clean_text(line)
    if len(line) < 8 or len(line) > 140:
        return False
    if line.endswith(".") and not re.match(r"^\d+(\.\d+)*\s+", line):
        return False
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


def parse_pdf(pdf_path: Path, tables_dir: Path, extract_tables: bool) -> tuple[dict, list[dict], list[dict]]:
    document_id = document_id_from_path(pdf_path)
    guideline_topic = pdf_path.parent.name
    pages = []
    tables = []

    with pdfplumber.open(pdf_path) as pdf:
        for index, page in enumerate(pdf.pages, start=1):
            text = clean_text(page.extract_text() or "")
            pages.append({"page": index, "text": text})

            if extract_tables:
                for table_index, table in enumerate(page.extract_tables() or [], start=1):
                    if not table:
                        continue
                    table_record = {
                        "document_id": document_id,
                        "source_type": "guideline",
                        "page": index,
                        "table_index": table_index,
                        "rows": table,
                        "metadata": {
                            "source": "guideline_pdf",
                            "guideline_topic": guideline_topic,
                            "source_file": str(pdf_path),
                        },
                    }
                    tables.append(table_record)

    document = {
        "document_id": document_id,
        "source_type": "guideline",
        "text": clean_text("\n\n".join(page["text"] for page in pages)),
        "metadata": {
            "source": "guideline_pdf",
            "guideline_topic": guideline_topic,
            "source_file": str(pdf_path),
            "page_count": len(pages),
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
                    "source": "guideline_pdf",
                    "guideline_topic": guideline_topic,
                    "source_file": str(pdf_path),
                    "page_start": section["page_start"],
                    "page_end": section["page_end"],
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


def parse_pdf_job(args: tuple[Path, Path, bool]) -> tuple[dict, list[dict], list[dict]]:
    return parse_pdf(*args)


def main() -> None:
    parser = argparse.ArgumentParser(description="Parse guideline PDFs into document, section, and table JSONL.")
    parser.add_argument("--input-dir", default="raw/guidelines", type=Path)
    parser.add_argument("--documents-output", default="processed/documents/guideline_documents.jsonl", type=Path)
    parser.add_argument("--sections-output", default="processed/sections/guideline_sections.jsonl", type=Path)
    parser.add_argument("--tables-dir", default="processed/tables", type=Path)
    parser.add_argument("--extract-tables", action="store_true")
    parser.add_argument(
        "--workers",
        default=max((os.cpu_count() or 2) - 1, 1),
        type=int,
        help="Number of PDFs to parse in parallel. Use 1 for deterministic single-process parsing.",
    )
    args = parser.parse_args()

    documents = []
    sections = []
    table_count = 0
    pdf_paths = sorted(args.input_dir.glob("*/*.pdf"))
    jobs = [(pdf_path, args.tables_dir, args.extract_tables) for pdf_path in pdf_paths]

    if args.workers == 1 or len(jobs) <= 1:
        results = [parse_pdf_job(job) for job in jobs]
    else:
        with ProcessPoolExecutor(max_workers=args.workers) as executor:
            results = list(executor.map(parse_pdf_job, jobs))

    for document, pdf_sections, tables in results:
        documents.append(document)
        sections.extend(pdf_sections)
        table_count += len(tables)

    write_jsonl(documents, args.documents_output)
    write_jsonl(sections, args.sections_output)
    print(
        f"Wrote {len(documents)} guideline documents, "
        f"{len(sections)} sections, and {table_count} tables"
    )


if __name__ == "__main__":
    main()
