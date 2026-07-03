import json
from pathlib import Path

from training.intake_finetune.convert_audit import convert_audit_jsonl


def test_convert_audit_jsonl_produces_sft_record(tmp_path: Path) -> None:
    audit_path = tmp_path / "audit.jsonl"
    audit_path.write_text(
        json.dumps(
            {
                "event_type": "chat_recommendation_completed",
                "payload": {
                    "message": "Benh nhan eGFR 24, kali 5.7, co nen tiep spironolactone?",
                    "patient": {
                        "case_id": "CASE_1",
                        "egfr": 24,
                        "potassium": 5.7,
                        "current_medications": ["spironolactone"],
                        "comorbidities": ["CKD"],
                        "allergies": [],
                    },
                },
            }
        )
        + "\n",
        encoding="utf-8",
    )
    records = convert_audit_jsonl(audit_path)
    assert len(records) == 1
    assert records[0]["messages"][1]["content"].startswith("Benh nhan")
    assert "spironolactone" in records[0]["messages"][2]["content"]
