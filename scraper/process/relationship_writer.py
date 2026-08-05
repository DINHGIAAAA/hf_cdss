"""Streaming JSONL writer with relationship_id deduplication."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class RelationshipWriter:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.seen: set[str] = set()
        self.count = 0
        path.parent.mkdir(parents=True, exist_ok=True)
        self._handle = path.open("w", encoding="utf-8", newline="\n")

    def add(self, rel: dict[str, Any]) -> None:
        key = rel.get("relationship_id")
        if not key or key in self.seen:
            return
        self.seen.add(key)
        self._handle.write(json.dumps(rel, ensure_ascii=False) + "\n")
        self.count += 1

    def add_many(self, rels: list[dict[str, Any]]) -> None:
        for rel in rels:
            self.add(rel)

    def close(self) -> None:
        self._handle.close()
