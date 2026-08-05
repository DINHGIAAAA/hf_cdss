"""Shared JSONL read/write helpers for scraper pipelines."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def iter_jsonl(path: Path):
    """Yield records one at a time (low RAM vs read_jsonl)."""
    if not path.exists():
        return
    with path.open(encoding="utf-8-sig") as handle:
        for line in handle:
            if line.strip():
                yield json.loads(line)


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return list(iter_jsonl(path))


def write_jsonl(records: list[dict[str, Any]], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
