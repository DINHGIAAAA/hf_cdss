import argparse
import json
import re
import xml.etree.ElementTree as ET
from pathlib import Path

from tqdm import tqdm

from scraper.transform.text_normalization import normalize_inline_text


NS = {"hl7": "urn:hl7-org:v3"}


def clean_text(value: str) -> str:
    return normalize_inline_text(value)


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


def first_attr(root: ET.Element, path: str, attr: str) -> str | None:
    node = root.find(path, NS)
    if node is None:
        return None
    value = node.attrib.get(attr)
    return value or None


def document_title(root: ET.Element) -> str | None:
    title = root.findtext("hl7:title", default="", namespaces=NS)
    return clean_text(title) or None


def dailymed_url(setid: str | None) -> str | None:
    if not setid:
        return None
    return f"https://dailymed.nlm.nih.gov/dailymed/drugInfo.cfm?setid={setid}"


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


def load_registry(path: Path | None) -> dict:
    if path is None or not path.exists():
        return {}
    registry = json.loads(path.read_text(encoding="utf-8-sig"))
    rows = {}
    for source in registry.get("sources", []):
        target_path = str(source.get("target_path", "")).replace("\\", "/")
        if target_path:
            rows[target_path] = source
            rows[Path(target_path).name] = source
        slug = source.get("slug")
        if slug:
            rows[slug] = source
    return rows


def infer_manifest_row(xml_path: Path, raw_dir: Path, manifest: dict, registry: dict | None = None) -> dict:
    slug = xml_path.parent.name
    rel = xml_path.relative_to(raw_dir).as_posix()
    registry = registry or {}
    registry_target = f"raw/drug_labels/{rel}"
    return (
        manifest.get(slug)
        or manifest.get(rel)
        or registry.get(registry_target)
        or registry.get(Path(rel).name)
        or registry.get(slug)
        or {"slug": slug, "query": slug.replace("_", " ")}
    )


def parse_xml(xml_path: Path, raw_dir: Path, manifest: dict, registry: dict | None = None) -> list[dict]:
    row = infer_manifest_row(xml_path, raw_dir, manifest, registry)
    root = ET.parse(xml_path).getroot()
    setid = row.get("setid") or first_attr(root, "hl7:setId", "root")
    spl_version = row.get("spl_version") or first_attr(root, "hl7:versionNumber", "value")
    published_date = row.get("published_date") or first_attr(root, "hl7:effectiveTime", "value")
    source_url = row.get("url") or row.get("source_url") or dailymed_url(setid)
    document_id = row.get("slug") or xml_path.stem.replace("_label", "")
    drug = (row.get("query") or document_id.replace("_", " ")).lower()
    title = row.get("title") or document_title(root) or f"{drug.title()} drug label"
    publisher = row.get("publisher") or "DailyMed"
    citation = f"{title}. {publisher}."

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
                    "source_type": "drug_label",
                    "source_url": source_url,
                    "publisher": publisher,
                    "published_date": published_date,
                    "retrieved_at": row.get("downloaded_at") or row.get("retrieved_at"),
                    "title": title,
                    "citation": citation,
                    "setid": setid,
                    "spl_version": spl_version,
                    "sha256": row.get("sha256"),
                    "storage_uri": row.get("storage_uri"),
                    "source_file": str(xml_path),
                    "page": None,
                    "provenance": {
                        "source_id": row.get("source_id") or document_id,
                        "source_url": source_url,
                        "section": section_name(section),
                        "setid": setid,
                        "spl_version": spl_version,
                    },
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
    parser = argparse.ArgumentParser(description="Parse DailyMed SPL XML labels to JSONL.")
    parser.add_argument("--input-dir", default="raw/drug_labels", type=Path)
    parser.add_argument("--manifest", default="artifacts/manifests/download_manifest.json", type=Path)
    parser.add_argument("--registry", default="sources/sources.example.json", type=Path)
    parser.add_argument(
        "--output",
        default="processed/sections/drug_label_sections.jsonl",
        type=Path,
        help="Write parsed sections to this JSONL file.",
    )
    args = parser.parse_args()

    manifest = load_manifest(args.manifest)
    registry = load_registry(args.registry)
    xml_paths = sorted(args.input_dir.glob("*/*_label.xml"))
    records: list[dict] = []

    print(f"Parsing {len(xml_paths)} XML files...")
    for xml_path in tqdm(xml_paths, desc="Parsing XML files"):
        records.extend(parse_xml(xml_path, args.input_dir, manifest, registry))

    write_jsonl(records, args.output)
    print("\n--- Processing Summary ---")
    print(f"Total XML files processed: {len(xml_paths)}")
    print(f"Total sections written to '{args.output}': {len(records)}")


if __name__ == "__main__":
    main()
