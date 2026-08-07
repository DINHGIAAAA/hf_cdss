"""Backfill chunk provenance (source_url / source_locator) and light mojibake repair.

Used after guideline HTML parse when registry lookup missed .html siblings of PDF targets.
"""

from __future__ import annotations

import argparse
import logging
import re
from pathlib import Path

from scraper.io.jsonl import read_jsonl, write_jsonl
from scraper.transform.parse_guideline_html import load_registry

logger = logging.getLogger(__name__)

_MOJIBAKE_REPLACEMENTS = (
    # Original entries (mojibake patterns as string literals)
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
    ("ÃÁ", "Á"),
    ("ÃÉ", "É"),
    ("ÃÍ", "Í"),
    ("ÃÓ", "Ó"),
    ("ÃÚ", "Ú"),
    ("â€™", "'"),
    ("â€˜", "'"),
    ("â€œ", '"'),
    ("â€¢", '"'),
    ("â€", '"'),
    ("â€", "-"),
    ("Ä", "đ"),
    ("Ä", "Đ"),
    # Expanded: C3 stray UTF-8 lead bytes (0x80-0xBF) from double-encoding
    ("Ã€", ""), ("Ã", ""), ("Ã", ""), ("Ã", ""), ("Ã", ""),
    ("Ã", ""), ("Ã", ""), ("Ã", ""), ("Ã", ""), ("Ã", ""),
    ("Ã", ""), ("Ã", ""), ("Ã", ""), ("Ã", ""), ("Ã", ""),
    ("Ã", ""), ("Ã", ""), ("Ã", ""), ("Ã", ""), ("Ã", ""),
    ("Ã", ""), ("Ã", ""), ("Ã", ""), ("Ã", ""), ("Ã", ""),
    ("Ã", ""), ("Ã", ""), ("Ã", ""), ("Ã", ""), ("Ã", ""),
    ("Ã", ""), ("Ã", ""), ("Ã", ""), ("Ã", ""), ("Ã", ""),
    ("Ã", ""), ("Ã", ""), ("Ã", ""), ("Ã", ""), ("Ã", ""),
    ("Ã", ""), ("Ã", ""), ("Ã", ""), ("Ã", ""), ("Ã", ""),
    ("Ã", ""), ("Ã", ""), ("Ã", ""), ("Ã", ""), ("Ã", ""),
    ("Ã", ""), ("Ã", ""), ("Ã", ""), ("Ã", ""), ("Ã", ""),
    ("Ã", ""), ("Ã", ""), ("Ã", ""), ("Ã", ""), ("Ã", ""),
    ("Ã", ""), ("Ã", ""), ("Ã", ""), ("Ã", ""), ("Ã", ""),
    ("Ã", ""), ("Ã", ""), ("Ã", ""), ("Ã", ""), ("Ã", ""),
    ("Ã", ""), ("Ã", ""), ("Ã", ""), ("Ã", ""), ("Ã", ""),
    # C2 stray lead bytes
    ("Â€", ""), ("Â", ""), ("Â", ""), ("Â", ""), ("Â", ""),
    ("Â", ""), ("Â", ""), ("Â", ""), ("Â", ""), ("Â", ""),
    ("Â", ""), ("Â", ""), ("Â", ""), ("Â", ""), ("Â", ""),
    ("Â", ""), ("Â", ""), ("Â", ""), ("Â", ""), ("Â", ""),
    ("Â", ""), ("Â", ""), ("Â", ""), ("Â", ""), ("Â", ""),
    ("Â", ""), ("Â", ""), ("Â", ""), ("Â", ""), ("Â", ""),
    ("Â", ""), ("Â", ""), ("Â", ""), ("Â", ""), ("Â", ""),
    ("Â", ""), ("Â", ""), ("Â", ""), ("Â", ""), ("Â", ""),
    ("Â", ""), ("Â", ""), ("Â", ""), ("Â", ""), ("Â", ""),
    ("Â", ""), ("Â", ""), ("Â", ""), ("Â", ""), ("Â", ""),
    ("Â", ""), ("Â", ""), ("Â", ""), ("Â", ""), ("Â", ""),
    ("Â", ""), ("Â", ""), ("Â", ""), ("Â", ""), ("Â", ""),
    ("Â", ""), ("Â", ""), ("Â", ""), ("Â", ""), ("Â", ""),
    ("Â", ""), ("Â", ""), ("Â", ""), ("Â", ""), ("Â", ""),
    ("Â", ""), ("Â", ""), ("Â", ""), ("Â", ""), ("Â", ""),
    # Common full sequences
    ("Â°", " deg"),
    ("Â²", "2"),
    ("Â³", "3"),
    ("Â©", "(C)"),
    ("Â®", "(R)"),
    ("â€" , "-"),
    ("â€" , "--"),
    ("â€' ", "'"),
    ("â€' ", "'"),
    ("â€" , '"'),
    ("â€" , '"'),
    ("â€", "..."),
    ("â€", ","),
    ("â€", ",,"),
    ("â" , "(TM)"),
    ("Ã—", "x"),
    ("Ã·", "/"),
    # Control characters
    ("\x00", ""),
    ("\x01", ""), ("\x02", ""), ("\x03", ""), ("\x04", ""), ("\x05", ""),
    ("\x06", ""), ("\x07", ""), ("\x08", ""), ("\x0b", ""), ("\x0c", ""),
    ("\x0e", ""), ("\x0f", ""), ("\x10", ""), ("\x11", ""), ("\x12", ""),
    ("\x13", ""), ("\x14", ""), ("\x15", ""), ("\x16", ""), ("\x17", ""),
    ("\x18", ""), ("\x19", ""), ("\x1a", ""), ("\x1c", ""), ("\x1d", ""),
    ("\x1e", ""), ("\x1f", ""), ("\x7f", ""),
)


def _fix_mojibake(text: str) -> str:
    if not text:
        return text
    repaired = text.replace("�", "")
    repaired = repaired.replace("\r\n", "\n").replace("\r", "\n")
    try:
        cand = repaired.encode("latin-1").decode("utf-8")
        if cand != repaired:
            repaired = cand
    except (UnicodeDecodeError, UnicodeEncodeError):
        pass
    repaired = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", repaired)
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

    meta = row.get("metadata") or {}
    source_ref = _resolve_source(meta, registry)
    if not meta.get("source_url") and source_ref.get("source_url"):
        meta["source_url"] = source_ref["source_url"]
        row["metadata"] = meta
        changed = True

    provenance = meta.get("provenance") or {}
    if not provenance.get("source_url") and source_ref.get("source_url"):
        provenance["source_url"] = source_ref["source_url"]
        if source_ref.get("source_id"):
            provenance["source_id"] = source_ref["source_id"]
        if source_ref.get("citation"):
            provenance["citation"] = source_ref["citation"]
        row.setdefault("metadata", meta)["provenance"] = provenance
        changed = True

    return row, changed


def repair_chunks(
    input_path: Path,
    registry: dict[str, dict],
    dry_run: bool = False,
) -> dict[str, int]:
    records = read_jsonl(input_path)
    changed_count = 0
    for row in records:
        _, changed = repair_chunk(row, registry)
        if changed:
            changed_count += 1

    if changed_count and not dry_run:
        write_jsonl(records, input_path)
        logger.info("Repaired provenance in %d/%d chunks: %s", changed_count, len(records), input_path)
    else:
        logger.info("Checked %d chunks: %d changed (dry run)", len(records), changed_count)

    return {"total": len(records), "changed": changed_count}


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    parser = argparse.ArgumentParser(description="Repair chunk provenance and mojibake.")
    parser.add_argument("--chunks", type=Path, required=True)
    parser.add_argument("--claims", type=Path, default=None)
    parser.add_argument(
        "--registry",
        type=Path,
        default=None,
        help="Path to sources registry JSON",
    )
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    registry = load_registry(args.registry)
    results: dict[str, dict] = {}

    if args.chunks.exists():
        results["chunks"] = repair_chunks(args.chunks, registry, args.dry_run)
    if args.claims and args.claims.exists():
        results["claims"] = repair_chunks(args.claims, registry, args.dry_run)

    total_changed = sum(r["changed"] for r in results.values())
    print(f"Repaired {total_changed} records across {len(results)} artifact types.")

    if not args.dry_run and total_changed == 0:
        print("Nothing to repair.")

    if total_changed and args.dry_run:
        print(f"Would repair {total_changed} records. Run without --dry-run to apply.")


if __name__ == "__main__":
    main()
