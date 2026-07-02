from __future__ import annotations

from typing import Any

from training.intake_finetune.prompts import load_intake_system_prompt
from training.intake_finetune.schema import dump_intake_label


def to_sft_record(user_text: str, label: dict[str, Any], *, source: str) -> dict[str, Any]:
    return {
        "messages": [
            {"role": "system", "content": load_intake_system_prompt()},
            {"role": "user", "content": user_text.strip()},
            {"role": "assistant", "content": dump_intake_label(label)},
        ],
        "metadata": {"source": source},
    }


def write_jsonl(path: str, records: list[dict[str, Any]]) -> None:
    import json
    from pathlib import Path

    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
