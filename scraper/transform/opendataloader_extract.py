"""Extract guideline PDF text and tables via OpenDataLoader PDF."""

from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Iterable

from scraper.transform.text_normalization import normalize_text

SKIP_ELEMENT_TYPES = frozenset({"header", "footer", "image", "formula"})
TEXT_ELEMENT_TYPES = frozenset({"heading", "paragraph", "caption", "list item"})


def java_available() -> bool:
    java = shutil.which("java")
    if not java:
        return False
    try:
        result = subprocess.run(
            [java, "-version"],
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError:
        return False
    return result.returncode == 0


def opendataloader_available() -> bool:
    if not java_available():
        return False
    try:
        import opendataloader_pdf  # noqa: F401
    except ImportError:
        return False
    return True


def json_output_path(pdf_path: Path, output_dir: Path) -> Path:
    return output_dir / f"{pdf_path.stem}.json"


def convert_pdfs(
    pdf_paths: list[Path],
    output_dir: Path,
    *,
    quiet: bool = True,
) -> None:
    if not pdf_paths:
        return
    import opendataloader_pdf

    output_dir.mkdir(parents=True, exist_ok=True)
    opendataloader_pdf.convert(
        input_path=[str(path) for path in pdf_paths],
        output_dir=str(output_dir),
        format="json",
        reading_order="xycut",
        image_output="off",
        quiet=quiet,
    )


def load_opendataloader_json(json_path: Path) -> dict[str, Any]:
    return json.loads(json_path.read_text(encoding="utf-8"))


def _node_page_number(node: dict[str, Any], fallback: int = 1) -> int:
    page = node.get("page number")
    if isinstance(page, int) and page > 0:
        return page
    return fallback


def _collect_text(node: dict[str, Any]) -> str:
    content = node.get("content")
    if isinstance(content, str) and content.strip():
        return normalize_text(content)

    parts: list[str] = []
    for key in ("kids", "list items"):
        children = node.get(key)
        if not isinstance(children, list):
            continue
        for child in children:
            if not isinstance(child, dict):
                continue
            text = _collect_text(child)
            if text:
                parts.append(text)
    return normalize_text(" ".join(parts))


def _table_rows(node: dict[str, Any]) -> list[list[str]]:
    rows_out: list[list[str]] = []
    rows = node.get("rows")
    if not isinstance(rows, list):
        return rows_out

    max_cols = 0
    parsed_rows: list[list[str]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        cells = row.get("cells")
        if not isinstance(cells, list):
            continue
        indexed_cells: dict[int, str] = {}
        for cell in cells:
            if not isinstance(cell, dict):
                continue
            column = cell.get("column number")
            if not isinstance(column, int) or column < 1:
                continue
            indexed_cells[column] = _collect_text(cell)
        if not indexed_cells:
            continue
        max_cols = max(max_cols, max(indexed_cells))
        parsed_rows.append(indexed_cells)

    for indexed_cells in parsed_rows:
        row_values = [indexed_cells.get(col, "") for col in range(1, max_cols + 1)]
        if any(value.strip() for value in row_values):
            rows_out.append(row_values)
    return rows_out


def _walk_elements(
    nodes: Iterable[Any],
    *,
    page_buffers: dict[int, list[str]],
    tables: list[tuple[int, list[list[str]]]],
    page_hint: int = 1,
) -> None:
    for node in nodes:
        if not isinstance(node, dict):
            continue

        element_type = str(node.get("type") or "").lower()
        page_number = _node_page_number(node, page_hint)

        if element_type in SKIP_ELEMENT_TYPES:
            continue

        if element_type == "table":
            table_rows = _table_rows(node)
            if table_rows:
                tables.append((page_number, table_rows))
            continue

        if element_type == "list":
            items = node.get("list items")
            if isinstance(items, list):
                for item in items:
                    if not isinstance(item, dict):
                        continue
                    text = _collect_text(item)
                    if text:
                        page_buffers.setdefault(_node_page_number(item, page_number), []).append(text)
            continue

        if element_type in TEXT_ELEMENT_TYPES:
            text = _collect_text(node)
            if text:
                if element_type == "heading":
                    page_buffers.setdefault(page_number, []).append(f"# {text}")
                else:
                    page_buffers.setdefault(page_number, []).append(text)
            continue

        for key in ("kids", "list items"):
            children = node.get(key)
            if isinstance(children, list):
                _walk_elements(children, page_buffers=page_buffers, tables=tables, page_hint=page_number)


def parse_opendataloader_document(document: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    page_buffers: dict[int, list[str]] = {}
    raw_tables: list[tuple[int, list[list[str]]]] = []

    kids = document.get("kids")
    if isinstance(kids, list):
        _walk_elements(kids, page_buffers=page_buffers, tables=raw_tables)

    page_count = document.get("number of pages")
    if isinstance(page_count, int) and page_count > 0:
        last_page = page_count
    elif page_buffers:
        last_page = max(page_buffers)
    else:
        last_page = 0

    pages: list[dict[str, Any]] = []
    for page_number in range(1, last_page + 1):
        lines = page_buffers.get(page_number, [])
        text = "\n".join(lines)
        pages.append({"page": page_number, "text": text})

    table_records: list[dict[str, Any]] = []
    for table_index, (page_number, rows) in enumerate(raw_tables, start=1):
        table_records.append(
            {
                "page": page_number,
                "table_index": table_index,
                "rows": rows,
            }
        )

    return pages, table_records


def extract_with_opendataloader(
    pdf_path: Path,
    *,
    cache_dir: Path | None = None,
    quiet: bool = True,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    if not opendataloader_available():
        raise RuntimeError("OpenDataLoader PDF is not available (requires Java and opendataloader-pdf).")

    owns_cache = cache_dir is None
    work_dir = cache_dir or Path(tempfile.mkdtemp(prefix="odl_pdf_"))
    try:
        json_path = json_output_path(pdf_path, work_dir)
        if not json_path.exists():
            convert_pdfs([pdf_path], work_dir, quiet=quiet)
        if not json_path.exists():
            raise FileNotFoundError(f"OpenDataLoader did not produce JSON for {pdf_path.name}")
        document = load_opendataloader_json(json_path)
        return parse_opendataloader_document(document)
    finally:
        if owns_cache:
            shutil.rmtree(work_dir, ignore_errors=True)
