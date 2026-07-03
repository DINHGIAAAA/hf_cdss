"""Export chat recommendation audit events as JSONL for intake fine-tuning."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def export_audit_sft_jsonl(
    *,
    output: Path,
    event_types: list[str] | None = None,
    limit: int = 5000,
) -> dict[str, int]:
    from app.modules.datastores.postgres import postgres_pool

    types = event_types or ["chat_recommendation_completed"]
    with postgres_pool().connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT id, case_id, event_type, payload, created_at
                FROM cdss_audit_events
                WHERE event_type = ANY(%s)
                ORDER BY created_at DESC
                LIMIT %s
                """,
                (types, max(1, min(limit, 50000))),
            )
            rows = cursor.fetchall()

    output.parent.mkdir(parents=True, exist_ok=True)
    exported = 0
    with output.open("w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            event = {
                "id": row[0],
                "case_id": row[1],
                "event_type": row[2],
                "payload": row[3] or {},
                "created_at": row[4].isoformat() if row[4] else None,
            }
            handle.write(json.dumps(event, ensure_ascii=False) + "\n")
            exported += 1
    return {"exported": exported, "output": str(output)}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Export audit events for intake SFT dataset building.")
    parser.add_argument("--output", type=Path, default=Path("training/data/audit_events.jsonl"))
    parser.add_argument("--limit", type=int, default=5000)
    parser.add_argument("--event-type", action="append", default=None)
    args = parser.parse_args()
    print(json.dumps(export_audit_sft_jsonl(output=args.output, event_types=args.event_type, limit=args.limit), indent=2))
