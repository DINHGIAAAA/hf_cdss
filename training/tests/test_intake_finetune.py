from __future__ import annotations

from pathlib import Path

from training.intake_finetune.convert_mimic_demo import convert_mimic_demo_directory
from training.intake_finetune.convert_n2c2 import convert_n2c2_directory


FIXTURES = Path(__file__).resolve().parents[1] / "intake_finetune" / "fixtures"


def test_convert_n2c2_fixture() -> None:
    records = convert_n2c2_directory(FIXTURES / "n2c2")
    assert len(records) == 1
    assistant = records[0]["messages"][2]["content"]
    assert "aspirin" in assistant
    assert "metoprolol" in assistant


def test_convert_mimic_demo_fixture() -> None:
    records = convert_mimic_demo_directory(FIXTURES / "mimic_demo" / "hosp")
    assert len(records) == 1
    assistant = records[0]["messages"][2]["content"]
    user = records[0]["messages"][1]["content"]
    assert "furosemide" in assistant
    assert "4.8" in assistant or "4.8" in user
    assert "Heart failure" in assistant
