"""Convert extracted PDF tables into guideline section records."""

from __future__ import annotations

import re


def _cell_text(value: object) -> str:
    if value is None:
        return ""
    return re.sub(r"\s+", " ", str(value)).replace("|", "\\|").strip()


def rows_to_markdown(rows: list[list[object]]) -> str:
    """Render table rows as a GitHub-flavored markdown table."""
    normalized: list[list[str]] = []
    for row in rows:
        if not row:
            continue
        cells = [_cell_text(cell) for cell in row]
        if any(cells):
            normalized.append(cells)
    if not normalized:
        return ""

    width = max(len(row) for row in normalized)
    padded = [row + [""] * (width - len(row)) for row in normalized]
    header = padded[0]
    lines = [
        "| " + " | ".join(header) + " |",
        "| " + " | ".join("---" for _ in range(width)) + " |",
    ]
    for row in padded[1:]:
        lines.append("| " + " | ".join(row) + " |")
    return "\n".join(lines)


def is_extracted_table_section(record: dict) -> bool:
    metadata = record.get("metadata") or {}
    if metadata.get("content_type") == "extracted_table":
        return True
    section = str(record.get("section") or "").strip().upper()
    return section.startswith("TABLE ") and bool((record.get("text") or "").strip())


def build_table_section_records(
    raw_tables: list[dict],
    *,
    document_id: str,
    provenance: dict,
    guideline_topic: str,
    source_file: str,
) -> tuple[list[dict], list[dict]]:
    """Return (raw table artifacts, section records with markdown text)."""
    table_records: list[dict] = []
    section_records: list[dict] = []

    for table in raw_tables:
        rows = table.get("rows") or []
        markdown = rows_to_markdown(rows)
        if not markdown:
            continue

        page = int(table["page"])
        table_index = int(table["table_index"])
        section_title = f"TABLE {table_index}"
        shared_metadata = {
            **provenance,
            "guideline_topic": guideline_topic,
            "source_file": source_file,
            "page": page,
            "page_start": page,
            "page_end": page,
            "section": section_title,
            "content_type": "extracted_table",
            "table_index": table_index,
            "provenance": {
                "source_id": provenance["source_id"],
                "source_url": provenance.get("source_url"),
                "page": page,
                "table_index": table_index,
                "section": section_title,
            },
        }

        table_records.append(
            {
                "document_id": document_id,
                "source_type": "guideline",
                "page": page,
                "table_index": table_index,
                "rows": rows,
                "metadata": dict(shared_metadata),
            }
        )
        section_records.append(
            {
                "document_id": document_id,
                "source_type": "guideline",
                "section": section_title,
                "text": markdown,
                "metadata": dict(shared_metadata),
            }
        )

    return table_records, section_records
