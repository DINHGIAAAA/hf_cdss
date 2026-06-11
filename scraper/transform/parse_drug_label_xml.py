import argparse
import json
import re
import xml.etree.ElementTree as ET
from pathlib import Path


NS = {"hl7": "urn:hl7-org:v3"}


def clean_text(value: str) -> str:
    value = re.sub(r"\s+", " ", value or "")
    return value.replace("\xa0", " ").strip()


def section_name(section: ET.Element) -> str:
    code = section.find("hl7:code", NS)
    display_name = code.attrib.get("displayName", "") if code is not None else ""
    title = clean_text(" ".join(section.findtext("hl7:title", default="", namespaces=NS).split()))

    raw = title or display_name or "UNTITLED"
    raw = re.sub(r"^\d+(\.\d+)*\s+", "", raw)
    raw = raw.replace(" SECTION", "")
    return clean_text(raw).upper()


def element_text(element: ET.Element) -> str:
    parts = []
    for text in element.itertext():
        text = clean_text(text)
        if text:
            parts.append(text)
    return clean_text(" ".join(parts))


def load_manifest(path: Path) -> dict:
    if not path.exists():
        return {}

    rows = json.loads(path.read_text(encoding="utf-8-sig"))
    manifest = {}
    for row in rows:
        manifest[row.get("slug")] = row
        if row.get("xml"):
            manifest[Path(row["xml"]).as_posix()] = row
    return manifest


def infer_manifest_row(xml_path: Path, raw_dir: Path, manifest: dict) -> dict:
    slug = xml_path.parent.name
    rel = xml_path.relative_to(raw_dir).as_posix()
    return manifest.get(slug) or manifest.get(rel) or {"slug": slug, "query": slug.replace("_", " ")}


def parse_xml(xml_path: Path, raw_dir: Path, manifest: dict) -> list[dict]:
    row = infer_manifest_row(xml_path, raw_dir, manifest)
    document_id = row.get("slug") or xml_path.stem.replace("_label", "")
    drug = (row.get("query") or document_id.replace("_", " ")).lower()
    title = row.get("title") or f"{drug.title()} drug label"
    publisher = row.get("publisher") or "DailyMed"
    citation = f"{title}. {publisher}."

    root = ET.parse(xml_path).getroot()
    records = []

    for section in root.findall(".//hl7:structuredBody/hl7:component/hl7:section", NS):
        text_node = section.find("hl7:text", NS)
        if text_node is None:
            continue

        text = element_text(text_node)
        if not text:
            continue

        records.append(
            {
                "document_id": document_id,
                "source_type": "drug_label",
                "section": section_name(section),
                "text": text,
                "metadata": {
                    "source_id": row.get("source_id") or document_id,
                    "drug": drug,
                    "source": "DailyMed",
                    "source_url": row.get("url"),
                    "publisher": publisher,
                    "published_date": row.get("published_date"),
                    "title": title,
                    "citation": citation,
                    "setid": row.get("setid"),
                    "spl_version": row.get("spl_version"),
                    "source_file": str(xml_path),
                },
            }
        )

    return records


def write_jsonl(records: list[dict], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="\n") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="Parse DailyMed SPL XML labels into section JSONL.")
    parser.add_argument("--input-dir", default="raw/drug_labels", type=Path)
    parser.add_argument("--manifest", default="artifacts/manifests/download_manifest.json", type=Path)
    parser.add_argument("--output", default="processed/sections/drug_label_sections.jsonl", type=Path)
    args = parser.parse_args()

    manifest = load_manifest(args.manifest)
    records = []
    for xml_path in sorted(args.input_dir.glob("*/*_label.xml")):
        records.extend(parse_xml(xml_path, args.input_dir, manifest))

    write_jsonl(records, args.output)
    print(f"Wrote {len(records)} drug label sections to {args.output}")


if __name__ == "__main__":
    main()
