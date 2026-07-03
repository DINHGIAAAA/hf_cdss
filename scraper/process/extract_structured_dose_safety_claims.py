"""Filter structured dose claims relevant to dose safety warnings."""

import argparse
import json
from pathlib import Path


def read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8-sig") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def write_jsonl(records: list[dict], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")


def filter_dose_safety_claims(records: list[dict]) -> list[dict]:
    output: list[dict] = []
    for record in records:
        if record.get("claim_type") == "structured_dose_safety_warning":
            output.append(record)
            continue
        if record.get("claim_type") != "structured_dose_rule":
            continue
        if record.get("monitoring") or record.get("lab_monitoring") or record.get("renal_adjustment"):
            output.append(record)
            continue
        haystack = " ".join(
            str(record.get(key) or "")
            for key in ("evidence", "notes", "message", "calculation_type")
        ).lower()
        if any(token in haystack for token in ("renal", "egfr", "potassium", "monitor", "heart rate")):
            output.append(record)
    return output


def main() -> None:
    parser = argparse.ArgumentParser(description="Extract dose safety warning claims from structured dose claims.")
    parser.add_argument("--input", default="artifacts/dose_rules/structured_dose_claims.jsonl", type=Path)
    parser.add_argument("--output", default="artifacts/dose_safety_warnings/structured_dose_safety_claims.jsonl", type=Path)
    args = parser.parse_args()

    claims = filter_dose_safety_claims(read_jsonl(args.input))
    write_jsonl(claims, args.output)
    print(f"Wrote {len(claims)} dose safety claims to {args.output}")


if __name__ == "__main__":
    main()
