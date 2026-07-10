"""Utilities for the canonical sources registry JSON file."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any

REGISTRY_PATH = Path(__file__).resolve().parents[2] / "data" / "heart_failure" / "sources" / "sources.example.json"

REQUIRED_FIELDS = {
    "guideline_html": {"source_id", "title", "source_type", "download_strategy", "publisher", "topic", "url", "target_path"},
    "guideline_pdf": {"source_id", "title", "source_type", "download_strategy", "publisher", "topic", "url", "target_path"},
    "drug_label_xml": {
        "source_id",
        "title",
        "source_type",
        "download_strategy",
        "publisher",
        "topic",
        "slug",
        "query",
        "required_terms",
        "target_path",
    },
}


def load_registry(path: Path = REGISTRY_PATH) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def write_registry(registry: dict[str, Any], path: Path = REGISTRY_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(registry, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def registry_stats(registry: dict[str, Any]) -> dict[str, Any]:
    sources = registry.get("sources", [])
    by_type = Counter(str(row.get("source_type")) for row in sources)
    by_topic = Counter(str(row.get("topic")) for row in sources)
    return {
        "total": len(sources),
        "by_type": dict(sorted(by_type.items())),
        "by_topic": dict(sorted(by_topic.items(), key=lambda item: (-item[1], item[0]))),
        "guideline_count": sum(1 for row in sources if str(row.get("source_type", "")).startswith("guideline_")),
        "drug_label_count": sum(1 for row in sources if row.get("source_type") == "drug_label_xml"),
    }


def validate_registry(registry: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    sources = registry.get("sources")
    if not isinstance(sources, list) or not sources:
        return ["registry.sources must be a non-empty list"]

    seen_ids: set[str] = set()
    for index, source in enumerate(sources, start=1):
        source_id = source.get("source_id")
        if not source_id:
            errors.append(f"source[{index}] missing source_id")
            continue
        if source_id in seen_ids:
            errors.append(f"duplicate source_id: {source_id}")
        seen_ids.add(source_id)

        source_type = source.get("source_type")
        required = REQUIRED_FIELDS.get(str(source_type))
        if required is None:
            errors.append(f"{source_id}: unsupported source_type={source_type}")
            continue
        missing = sorted(required - set(source.keys()))
        if missing:
            errors.append(f"{source_id}: missing fields {missing}")

    return errors


def _sort_key(source: dict[str, Any]) -> tuple:
    source_type = str(source.get("source_type", ""))
    is_drug = 0 if source_type.startswith("guideline_") else 1
    return (is_drug, str(source.get("topic", "")), str(source.get("source_id", "")))


def normalize_registry(registry: dict[str, Any]) -> dict[str, Any]:
    sources = registry.get("sources", [])
    deduped: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for source in sources:
        source_id = source.get("source_id")
        if not source_id or source_id in seen_ids:
            continue
        seen_ids.add(source_id)
        deduped.append(source)

    deduped.sort(key=_sort_key)
    registry = dict(registry)
    registry["sources"] = deduped
    registry["source_summary"] = registry_stats(registry)
    return registry


def print_registry_report(path: Path = REGISTRY_PATH) -> int:
    registry = load_registry(path)
    errors = validate_registry(registry)
    stats = registry.get("source_summary") or registry_stats(registry)

    print(f"Registry: {path}")
    print(f"Version: {registry.get('version')}")
    print(f"Total sources: {stats['total']} ({stats['guideline_count']} guidelines, {stats['drug_label_count']} drug labels)")
    print("By type:", stats["by_type"])
    print("By topic:", stats["by_topic"])

    if errors:
        print("\nValidation errors:")
        for error in errors:
            print(f"  - {error}")
        return 1

    print("\nValidation: OK")
    return 0


def main() -> None:
    registry = normalize_registry(load_registry())
    errors = validate_registry(registry)
    if errors:
        for error in errors:
            print(error)
        raise SystemExit(1)
    write_registry(registry)
    raise SystemExit(print_registry_report())


if __name__ == "__main__":
    main()
