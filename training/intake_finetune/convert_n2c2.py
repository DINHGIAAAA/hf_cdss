from __future__ import annotations

from pathlib import Path
from typing import Iterator

from training.intake_finetune.brat_parser import load_brat_document, medications_from_brat, red_flags_from_brat
from training.intake_finetune.schema import empty_intake_label
from training.intake_finetune.sft_format import to_sft_record


def _iter_note_pairs(root: Path) -> Iterator[tuple[Path, Path]]:
    text_files = sorted(root.rglob("*.txt"))
    if not text_files:
        text_files = sorted(root.rglob("*.text"))
    for text_path in text_files:
        ann_path = text_path.with_suffix(".ann")
        if ann_path.exists():
            yield text_path, ann_path


def convert_n2c2_directory(root: Path) -> list[dict]:
    records: list[dict] = []
    for text_path, ann_path in _iter_note_pairs(root):
        document = load_brat_document(text_path, ann_path)
        if not document.text.strip():
            continue
        medications = medications_from_brat(document)
        if not medications and not red_flags_from_brat(document):
            continue
        label = empty_intake_label()
        label["medications"] = medications
        label["red_flags"] = red_flags_from_brat(document)
        label["chief_complaint"] = "Medication review from discharge summary."
        records.append(
            to_sft_record(
                document.text,
                label,
                source=f"n2c2:{text_path.stem}",
            )
        )
    return records
