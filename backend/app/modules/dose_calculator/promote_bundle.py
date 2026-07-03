"""Copy and validate a new dose-rules bundle version (v1 → v2 rollout helper)."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from app.modules.dose_calculator.bundle_paths import dose_rules_bundle_dir, _version_suffix
from app.modules.dose_calculator.rule_validation import DoseRulesValidationError, validate_bundle_file


def promote_bundle(*, from_version: str, to_version: str, overwrite: bool = False) -> Path:
    src = dose_rules_bundle_dir() / f"hf_dose_rules_v{_version_suffix(from_version)}.json"
    dst = dose_rules_bundle_dir() / f"hf_dose_rules_v{_version_suffix(to_version)}.json"
    target_label = f"hf_dose_rules_v{_version_suffix(to_version)}"

    if not src.is_file():
        raise FileNotFoundError(f"Source bundle not found: {src}")
    if dst.is_file() and not overwrite:
        raise FileExistsError(f"Target already exists: {dst} (pass --overwrite)")

    payload = json.loads(src.read_text(encoding="utf-8"))
    payload["version"] = target_label
    payload["_promoted_from"] = str(src.name)
    dst.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    validate_bundle_file(dst, strict=True)
    return dst


def main() -> int:
    parser = argparse.ArgumentParser(description="Promote dose rules bundle to a new version file")
    parser.add_argument("--from", dest="from_version", default="v1", help="Source bundle version (default: v1)")
    parser.add_argument("--to", dest="to_version", required=True, help="Target bundle version (e.g. v2)")
    parser.add_argument("--overwrite", action="store_true", help="Overwrite target file if present")
    args = parser.parse_args()

    try:
        path = promote_bundle(
            from_version=args.from_version,
            to_version=args.to_version,
            overwrite=args.overwrite,
        )
    except (DoseRulesValidationError, FileNotFoundError, FileExistsError) as exc:
        print(f"promote_bundle failed: {exc}", file=sys.stderr)
        return 1

    print(f"Created validated bundle: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
