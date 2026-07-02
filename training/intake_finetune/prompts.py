from __future__ import annotations

from pathlib import Path


_FALLBACK = Path(__file__).resolve().parents[2] / "backend" / "app" / "prompts" / "clinical_intake.py"


def load_intake_system_prompt() -> str:
    try:
        from app.prompts.clinical_intake import CLINICAL_INTAKE_SYSTEM_PROMPT

        return CLINICAL_INTAKE_SYSTEM_PROMPT
    except ImportError:
        namespace: dict = {}
        exec(_FALLBACK.read_text(encoding="utf-8"), namespace)
        return str(namespace["CLINICAL_INTAKE_SYSTEM_PROMPT"])
