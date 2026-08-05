"""Seed one demo patient + chat conversation in Postgres (idempotent)."""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from app.modules.datastores.postgres import append_chat_message, upsert_patient_draft
from app.schemas.patient import PatientProfile

CONVERSATION_ID = "demo_tran_minh_hfref"
_SEED_JSON = Path(__file__).with_name("demo_chat_seed.json")


def _load_seed() -> dict:
    raw = json.loads(_SEED_JSON.read_text(encoding="utf-8"))
    if not raw:
        raise SystemExit("demo_chat_conversation.json is empty")
    return raw[0]


def main() -> int:
    seed = _load_seed()
    patient = PatientProfile.model_validate(seed["patient"])
    now = datetime.now(timezone.utc)

    upsert_patient_draft(
        {
            "conversation_id": CONVERSATION_ID,
            "patient": patient.model_dump(mode="json"),
            "source": "seed_demo_chat",
            "updated_at": now,
        }
    )

    for msg in seed.get("messages", []):
        append_chat_message(
            {
                "message_id": msg["id"],
                "conversation_id": CONVERSATION_ID,
                "role": msg["role"],
                "content": msg["content"],
                "metadata": {},
                "created_at": now,
            }
        )

    print(
        json.dumps(
            {
                "conversation_id": CONVERSATION_ID,
                "case_id": patient.case_id,
                "patient_name": patient.patient_identity.full_name,
                "messages": len(seed.get("messages", [])),
                "history_url": f"/api/v1/chat/{CONVERSATION_ID}/history",
                "local_storage_file": "data/demo/demo_chat_conversation.json (import in browser)",
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
