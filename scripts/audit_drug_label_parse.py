"""Audit parse success across all FDA drug label XMLs."""
from __future__ import annotations

from collections import Counter
from pathlib import Path

from app.modules.dose_calculation.convert_extracted_doses import build_drug_entry
from app.modules.dose_calculation.xml_dose_extractor import parse_drug_label


def main() -> None:
    root = Path("data/heart_failure/raw/drug_labels")
    xmls = sorted(root.rglob("*_label.xml"))
    ok, thin, fail = [], [], []

    for xml in xmls:
        pid = xml.parent.name
        try:
            data = parse_drug_label(xml)
            entry = build_drug_entry(data)
            doses = 0
            for form in entry.get("formulations") or []:
                doses += len(form.get("doses") or [])
            renal = len(entry.get("renal_adjustments") or [])
            multi = len(entry.get("multi_factor_adjustments") or [])
            potassium = len(entry.get("potassium_adjustments") or [])
            heart_rate = len(entry.get("heart_rate_adjustments") or [])
            usable = bool(
                doses
                or renal
                or multi
                or entry.get("starting_dose")
                or entry.get("target_dose")
            )
            row = {
                "pipeline_id": pid,
                "drug_key": entry.get("drug_key"),
                "class": entry.get("drug_class"),
                "doses": doses,
                "renal": renal,
                "multi": multi,
                "K": potassium,
                "HR": heart_rate,
            }
            (ok if usable else thin).append(row)
        except Exception as exc:  # noqa: BLE001
            fail.append({"pipeline_id": pid, "error": f"{type(exc).__name__}: {exc}"})

    print(f"TOTAL XML: {len(xmls)}")
    print(f"PARSE OK + has dose signal: {len(ok)}")
    print(f"PARSE OK but thin (no dose/renal/multi): {len(thin)}")
    print(f"PARSE FAIL: {len(fail)}")
    print()
    if fail:
        print("=== PARSE FAILURES ===")
        for row in fail:
            print(f"  {row['pipeline_id']}: {row['error']}")
        print()
    if thin:
        print("=== THIN (parsed but no extracted dose rules) ===")
        for row in sorted(thin, key=lambda item: item["pipeline_id"]):
            print(
                f"  {row['pipeline_id']} -> {row['drug_key']} [{row['class']}] "
                f"doses={row['doses']} renal={row['renal']} multi={row['multi']} "
                f"K={row['K']} HR={row['HR']}"
            )
        print()
        print("thin by class:", dict(Counter(row["class"] for row in thin)))


if __name__ == "__main__":
    main()
