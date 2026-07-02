from __future__ import annotations

import argparse
import json
from pathlib import Path

from training.intake_finetune.convert_mimic_demo import convert_mimic_demo_directory
from training.intake_finetune.convert_n2c2 import convert_n2c2_directory
from training.intake_finetune.sft_format import write_jsonl


def build_dataset(
    *,
    n2c2_dir: Path | None,
    mimic_hosp_dir: Path | None,
    output: Path,
    include_all_mimic: bool = False,
) -> dict[str, int]:
    records: list[dict] = []
    stats = {"n2c2": 0, "mimic_demo": 0}

    if n2c2_dir:
        n2c2_records = convert_n2c2_directory(n2c2_dir)
        records.extend(n2c2_records)
        stats["n2c2"] = len(n2c2_records)

    if mimic_hosp_dir:
        mimic_records = convert_mimic_demo_directory(mimic_hosp_dir, hf_only=not include_all_mimic)
        records.extend(mimic_records)
        stats["mimic_demo"] = len(mimic_records)

    if not records:
        raise RuntimeError("No SFT records produced. Check dataset paths and credentials.")

    write_jsonl(str(output), records)
    manifest = {
        "output": str(output),
        "total_records": len(records),
        **stats,
    }
    manifest_path = output.with_suffix(".manifest.json")
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description="Build Phase 1 clinical intake SFT dataset (n2c2 + MIMIC demo).")
    parser.add_argument("--n2c2-dir", type=Path, help="Path to n2c2 2018 Track 2 text/ann folder")
    parser.add_argument("--mimic-hosp-dir", type=Path, help="Path to MIMIC-IV demo hosp/ CSV folder")
    parser.add_argument("--output", type=Path, default=Path("training/data/intake_sft.jsonl"))
    parser.add_argument(
        "--include-all-mimic",
        action="store_true",
        help="Do not filter MIMIC admissions to heart-failure ICD codes",
    )
    args = parser.parse_args()

    if not args.n2c2_dir and not args.mimic_hosp_dir:
        parser.error("Provide at least one of --n2c2-dir or --mimic-hosp-dir")

    manifest = build_dataset(
        n2c2_dir=args.n2c2_dir,
        mimic_hosp_dir=args.mimic_hosp_dir,
        output=args.output,
        include_all_mimic=args.include_all_mimic,
    )
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
