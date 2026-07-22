from scraper.io.jsonl import read_jsonl, write_jsonl
import argparse
import html
import json
import re
import traceback
from html.parser import HTMLParser
from pathlib import Path

from tqdm import tqdm

from scraper.transform.text_normalization import normalize_text

class ArticleHTMLParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.capture_tag: str | None = None
        self.current: list[str] = []
        self.blocks: list[tuple[str, str]] = []
        self.skip_depth = 0

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag in {"script", "style", "nav", "header", "footer", "aside"}:
            self.skip_depth += 1
            return
        if self.skip_depth:
            return
        if tag in {"h1", "h2", "h3", "p", "li"}:
            self.capture_tag = tag
            self.current = []

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style", "nav", "header", "footer", "aside"} and self.skip_depth:
            self.skip_depth -= 1
            return
        if tag == self.capture_tag:
            text = normalize_text(html.unescape(" ".join(self.current)))
            text = re.sub(r"\s+", " ", text).strip()
            if len(text) >= 20:
                self.blocks.append((tag, text))
            self.capture_tag = None
            self.current = []

    def handle_data(self, data: str) -> None:
        if self.capture_tag and not self.skip_depth:
            self.current.append(data)

def load_registry(path: Path | None) -> dict[str, dict]:
    if path is None or not path.exists():
        return {}
    registry = json.loads(path.read_text(encoding="utf-8-sig"))
    rows = {}
    for source in registry.get("sources", []):
        target_path = str(source.get("target_path", "")).replace("\\", "/")
        rows[target_path] = source
        rows[Path(target_path).name] = source
    return rows

def source_metadata(path: Path, registry: dict[str, dict]) -> dict:
    source = registry.get(path.name) or registry.get(path.as_posix()) or {}
    if not source:
        normalized_path = path.as_posix()
        for target_path, row in registry.items():
            if "/" in target_path and normalized_path.endswith(target_path):
                source = row
                break
    citation = source.get("title") or path.stem
    publisher = source.get("publisher")
    if publisher:
        citation = f"{citation}. {publisher}."
    return {
        "source_id": source.get("source_id") or path.stem,
        "source": "guideline_html",
        "source_type": "guideline",
        "source_url": source.get("url"),
        "publisher": publisher,
        "title": source.get("title") or path.stem,
        "citation": citation,
        "license_note": source.get("license_note"),
        "topic": source.get("topic"),
    }

def slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-") or "section"

def parse_sections(path: Path, registry: dict[str, dict]) -> list[dict]:
    metadata = source_metadata(path, registry)
    parser = ArticleHTMLParser()
    parser.feed(path.read_text(encoding="utf-8-sig", errors="ignore"))
    sections: list[dict] = []
    current_heading = "ARTICLE"
    current_text: list[str] = []

    for tag, text in parser.blocks:
        if tag in {"h1", "h2", "h3"}:
            if current_text:
                sections.append(_section_record(path, metadata, current_heading, current_text))
                current_text = []
            current_heading = text[:180].upper()
        else:
            current_text.append(text)

    if current_text:
        sections.append(_section_record(path, metadata, current_heading, current_text))
    return sections

def _section_record(path: Path, metadata: dict, section: str, lines: list[str]) -> dict:
    text = normalize_text("\n".join(lines))
    section_anchor = slug(section)
    source_url = metadata.get("source_url")
    source_locator = f"{source_url}#{section_anchor}" if source_url else None
    return {
        "document_id": metadata["source_id"],
        "source_type": "guideline",
        "section": section,
        "text": text,
        "metadata": {
            **metadata,
            "source_file": str(path),
            "page": None,
            "section_anchor": section_anchor,
            "source_locator": source_locator,
            "provenance": {
                "source_id": metadata["source_id"],
                "source_url": source_url,
                "source_locator": source_locator,
                "section": section,
                "section_anchor": section_anchor,
            },
        },
    }

def main() -> None:
    from scraper.paths import guidelines_dir

    parser = argparse.ArgumentParser(description="Parse guideline HTML pages to JSONL.")
    parser.add_argument(
        "--input-dir",
        default=None,
        type=Path,
        help="Guideline HTML root (default: HF_CDSS_RAW_ROOT/guidelines).",
    )
    parser.add_argument("--registry", default="sources/sources.example.json", type=Path)
    parser.add_argument("--sections-output", default="processed/sections/guideline_html_sections.jsonl", type=Path)
    args = parser.parse_args()
    input_dir = args.input_dir or guidelines_dir()

    registry = load_registry(args.registry)
    html_paths = sorted(input_dir.glob("**/*.html"))
    sections: list[dict] = []

    print(f"Parsing {len(html_paths)} HTML files from {input_dir}...")
    for path in tqdm(html_paths, desc="Parsing HTML files"):
        try:
            sections.extend(parse_sections(path, registry))
        except Exception as exc:
            print(f"\n[ERROR] Failed to parse HTML file: {path}")
            print(f"Details: {exc}")
            traceback.print_exc()

    write_jsonl(sections, args.sections_output)
    print(f"Wrote {len(sections)} sections to {args.sections_output}")

if __name__ == "__main__":
    main()
