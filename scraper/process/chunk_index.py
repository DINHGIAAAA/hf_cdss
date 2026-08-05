"""Document-scoped chunk lookup for derive_relationships (memory or SQLite)."""

from __future__ import annotations

import json
import os
import sqlite3
import tempfile
from collections import defaultdict
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from scraper.io.jsonl import iter_jsonl

_MISSING_DOC_KEY = ""


def _use_sqlite_index(path: Path) -> bool:
    explicit = os.environ.get("HF_CDSS_DERIVE_LOW_MEMORY", "").lower() in {"1", "true", "yes"}
    if explicit:
        return True
    threshold_mb = int(os.environ.get("HF_CDSS_DERIVE_SQLITE_THRESHOLD_MB", "400"))
    size_mb = path.stat().st_size / (1024 * 1024)
    return size_mb >= threshold_mb


class MemoryChunkIndex:
    """Chunks grouped by document_id (one pass over JSONL)."""

    def __init__(self, *, by_document: dict[str, list[dict[str, Any]]]) -> None:
        self._by_document = by_document

    @classmethod
    def from_path(cls, path: Path) -> MemoryChunkIndex:
        by_document: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for chunk in iter_jsonl(path):
            doc = str(chunk.get("document_id") or _MISSING_DOC_KEY)
            by_document[doc].append(chunk)
        return cls(by_document=dict(by_document))

    @classmethod
    def from_records(cls, chunks: list[dict[str, Any]]) -> MemoryChunkIndex:
        by_document: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for chunk in chunks:
            doc = str(chunk.get("document_id") or _MISSING_DOC_KEY)
            by_document[doc].append(chunk)
        return cls(by_document=dict(by_document))

    def chunks_for_claim(self, claim: dict[str, Any]) -> list[dict[str, Any]]:
        document_id = claim.get("document_id")
        if document_id:
            return list(self._by_document.get(str(document_id), []))
        return list(self._by_document.get(_MISSING_DOC_KEY, []))

    def iter_chunks(self) -> Iterator[dict[str, Any]]:
        for chunks in self._by_document.values():
            yield from chunks

    def close(self) -> None:
        return


class SqliteChunkIndex:
    """Spill chunks to a temp SQLite DB; query by document_id only."""

    def __init__(self, path: Path) -> None:
        fd, raw_path = tempfile.mkstemp(prefix="hf_cdss_chunks_", suffix=".sqlite")
        os.close(fd)
        self._db_path = Path(raw_path)
        self._conn = sqlite3.connect(self._db_path)
        self._conn.execute(
            "CREATE TABLE chunks (document_id TEXT NOT NULL, payload TEXT NOT NULL)"
        )
        self._conn.execute("CREATE INDEX idx_chunks_document ON chunks(document_id)")
        batch: list[tuple[str, str]] = []
        loaded = 0
        for chunk in iter_jsonl(path):
            doc = str(chunk.get("document_id") or _MISSING_DOC_KEY)
            batch.append((doc, json.dumps(chunk, ensure_ascii=False)))
            loaded += 1
            if len(batch) >= 200:
                self._conn.executemany("INSERT INTO chunks VALUES (?, ?)", batch)
                batch.clear()
        if batch:
            self._conn.executemany("INSERT INTO chunks VALUES (?, ?)", batch)
        self._conn.commit()
        print(f"[derive_relationships] sqlite chunk index: loaded {loaded} chunks", flush=True)

    def chunks_for_claim(self, claim: dict[str, Any]) -> list[dict[str, Any]]:
        document_id = claim.get("document_id")
        key = str(document_id) if document_id else _MISSING_DOC_KEY
        cursor = self._conn.execute("SELECT payload FROM chunks WHERE document_id = ?", (key,))
        return [json.loads(row[0]) for row in cursor]

    def iter_chunks(self) -> Iterator[dict[str, Any]]:
        cursor = self._conn.execute("SELECT payload FROM chunks")
        for (payload,) in cursor:
            yield json.loads(payload)

    def close(self) -> None:
        self._conn.close()
        try:
            self._db_path.unlink(missing_ok=True)
        except OSError:
            pass


class EmptyChunkIndex:
    def chunks_for_claim(self, claim: dict[str, Any]) -> list[dict[str, Any]]:
        return []

    def iter_chunks(self) -> Iterator[dict[str, Any]]:
        return iter(())

    def close(self) -> None:
        return


def open_chunk_index(path: Path) -> MemoryChunkIndex | SqliteChunkIndex | EmptyChunkIndex:
    if not path.is_file():
        return EmptyChunkIndex()
    size_mb = path.stat().st_size / (1024 * 1024)
    if _use_sqlite_index(path):
        print(
            f"[derive_relationships] using SQLite chunk index ({size_mb:.0f} MB file; "
            "set HF_CDSS_DERIVE_LOW_MEMORY=0 to force in-memory)",
            flush=True,
        )
        return SqliteChunkIndex(path)
    print(
        f"[derive_relationships] using in-memory chunk index by document_id ({size_mb:.0f} MB file)",
        flush=True,
    )
    return MemoryChunkIndex.from_path(path)
