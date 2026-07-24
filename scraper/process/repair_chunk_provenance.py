"""Backfill chunk provenance (source_url / source_locator) and light mojibake repair.

Used after guideline HTML parse when registry lookup missed .html siblings of PDF targets.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from scraper.io.jsonl import read_jsonl, write_jsonl
from scraper.transform.parse_guideline_html import load_registry

_MOJIBAKE_REPLACEMENTS = (
    ("Ã¡", "á"),
    ("Ã©", "é"),
    ("Ã­", "í"),
    ("Ã³", "ó"),
    ("Ãº", "ú"),
    ("Ã±", "ñ"),
    ("Ã¼", "ü"),
    ("Ã§", "ç"),
    ("Ã¤", "ä"),
    ("Ã¶", "ö"),
    ("Ã", "Á"),
    ("Ã‰", "É"),
    ("Ã", "Í"),
    ("Ã“", "Ó"),
    ("Ãš", "Ú"),
    ("â€™", "'"),
    ("â€˜", "'"),
    ("â€œ", '"'),
    ("â€", '"'),
    ("â€“", "-"),
    ("â€”", "-"),
    ("â€", '"'),
    ("Ä‘", "đ"),
    ("Ä", "Đ"),
)


def _fix_mojibake(text: str) -> str:
    if not text:
        return text
    repaired = text.replace("\ufffd", "")
    try:
        candidate = repaired.encode("latin-1").decode("utf-8")
        if candidate and candidate != repaired:
            return candidate
    except (UnicodeDecodeError, UnicodeEncodeError):
        pass
    for bad, good in _MOJIBAKE_REPLACEMENTS:
        if bad in repaired:
            repaired = repaired.replace(bad, good)
    return repaired


def _resolve_source(meta: dict, registry: dict[str, dict]) -> dict:
    source_file = str(meta.get("source_file") or "")
    source_id = str(meta.get("source_id") or "")
    document_hint = Path(source_file).stem if source_file else source_id
    return (
        registry.get(Path(source_file).name)
        or registry.get(document_hint)
        or registry.get(f"{document_hint}.html")
        or registry.get(f"{document_hint}.pdf")
        or registry.get(source_id)
        or {}
    )


def repair_chunk(row: dict, registry: dict[str, dict]) -> tuple[dict, bool]:
    changed = False
    text = str(row.get("text") or "")
    fixed_text = _fix_mojibake(text)
    if fixed_text != text:
        row["text"] = fixed_text
        changed = True

    meta = dict(row.get("metadata") or {})
    provenance = dict(meta.get("provenance") or {})
    source = _resolve_source(meta, registry)

    source_url = meta.get("source_url") or source.get("html_url") or source.get("url")
    if source_url and meta.get("source_url") != source_url:
        meta["source_url"] = source_url
        changed = True

    if source.get("source_id") and not meta.get("source_id"):
        meta["source_id"] = source["source_id"]
        changed = True

    if source.get("title") and not meta.get("citation"):
        citation = source["title"]
        if source.get("publisher"):
            citation = f"{citation}. {source['publisher']}."
        meta["citation"] = citation
        changed = True

    source_locator = meta.get("source_locator") or provenance.get("source_locator")
    if not source_locator and source_url:
        page = meta.get("page_start") or meta.get("page")
        source_locator = f"{source_url}#page={page}" if page else source_url
        meta["source_locator"] = source_locator
        changed = True

    if source_locator and provenance.get("source_locator") != source_locator:
        provenance["source_locator"] = source_locator
        changed = True
    if source_url and provenance.get("source_url") != source_url:
        provenance["source_url"] = source_url
        changed = True

    if changed:
        meta["provenance"] = provenance
        row["metadata"] = meta
    return row, changed


def repair_claim(row: dict) -> tuple[dict, bool]:
    evidence = str(row.get("evidence") or "")
    fixed = _fix_mojibake(evidence)
    if fixed == evidence:
        return row, False
    row["evidence"] = fixed
    return row, True


def main() -> None:
    parser = argparse.ArgumentParser(description="Repair chunk source_url / locator / mojibake.")
    parser.add_argument("--chunks", default=Path("artifacts/chunks/chunks.jsonl"), type=Path)
    parser.add_argument("--claims", default=Path("artifacts/claims/claims.jsonl"), type=Path)
    parser.add_argument(
        "--registry",
        default=Path("sources/sources.example.json"),
        type=Path,
        help="Sources registry used to backfill URLs by filename stem.",
    )
    args = parser.parse_args()

    registry = load_registry(args.registry)
    rows = read_jsonl(args.chunks)
    changed_count = 0
    fixed_rows = []
    for row in rows:
        fixed, changed = repair_chunk(row, registry)
        fixed_rows.append(fixed)
        if changed:
            changed_count += 1
    write_jsonl(fixed_rows, args.chunks)
    print(f"Repaired {changed_count}/{len(fixed_rows)} chunks in {args.chunks}")

    if args.claims.exists():
        claim_rows = read_jsonl(args.claims)
        claim_changed = 0
        fixed_claims = []
        for row in claim_rows:
            fixed, changed = repair_claim(row)
            fixed_claims.append(fixed)
            if changed:
                claim_changed += 1
        write_jsonl(fixed_claims, args.claims)
        print(f"Repaired {claim_changed}/{len(fixed_claims)} claims in {args.claims}")


if __name__ == "__main__":
    main()
