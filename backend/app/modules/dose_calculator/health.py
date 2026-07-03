"""Dose rules governance readiness probe."""

from __future__ import annotations

from typing import Any

from app.core.config import settings


def dose_rules_status() -> dict[str, Any]:
    if not settings.dose_calculator_enabled:
        return {"status": "disabled"}

    try:
        from app.modules.dose_calculator.rule_validation import DoseRulesValidationError, check_runtime_dose_rules

        return check_runtime_dose_rules()
    except DoseRulesValidationError as exc:
        return {"status": "error", "detail": str(exc), "errors": exc.errors}
    except Exception as exc:
        return {"status": "error", "detail": str(exc)}
