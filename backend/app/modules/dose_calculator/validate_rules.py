"""CLI: validate all bundled hf_dose_rules_v*.json files (CI / pre-deploy)."""

from __future__ import annotations

import json
import sys

from app.modules.dose_calculator.rule_validation import DoseRulesValidationError, validate_all_bundled_versions


def main() -> int:
    try:
        results = validate_all_bundled_versions()
    except DoseRulesValidationError as exc:
        print(f"dose rules validation failed: {exc}", file=sys.stderr)
        for error in exc.errors:
            print(f"  - {error}", file=sys.stderr)
        return 1

    print(json.dumps({"status": "ok", "bundles": results}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
