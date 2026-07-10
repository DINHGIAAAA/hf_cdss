from pathlib import Path

from scraper.scripts.sources_registry import (
    REGISTRY_PATH,
    load_registry,
    normalize_registry,
    registry_stats,
    validate_registry,
    write_registry,
)


def test_canonical_registry_file_is_valid() -> None:
    registry = load_registry(REGISTRY_PATH)
    errors = validate_registry(registry)
    assert errors == [], errors
    stats = registry_stats(registry)
    assert stats["total"] >= 90
    assert stats["drug_label_count"] >= 40
    assert stats["guideline_count"] >= 45


def test_normalize_registry_dedupes_and_adds_summary(tmp_path: Path) -> None:
    registry_path = tmp_path / "sources.example.json"
    registry_path.write_text(
        """
        {
          "version": 4,
          "sources": [
            {"source_id": "dup", "source_type": "guideline_pdf", "title": "A", "download_strategy": "direct_url", "publisher": "X", "topic": "heart_failure", "url": "https://example.org/a.pdf", "target_path": "raw/a.pdf"},
            {"source_id": "dup", "source_type": "guideline_pdf", "title": "A", "download_strategy": "direct_url", "publisher": "X", "topic": "heart_failure", "url": "https://example.org/a.pdf", "target_path": "raw/a.pdf"},
            {"source_id": "drug", "source_type": "drug_label_xml", "title": "Drug", "download_strategy": "dailymed_spl", "publisher": "DailyMed", "topic": "drug_label", "slug": "drug", "query": "DRUG", "required_terms": ["DRUG"], "target_path": "raw/drug.xml"}
          ]
        }
        """.strip(),
        encoding="utf-8",
    )

    normalized = normalize_registry(load_registry(registry_path))
    write_registry(normalized, registry_path)

    payload = load_registry(registry_path)
    assert len(payload["sources"]) == 2
    assert payload["source_summary"]["total"] == 2
    assert validate_registry(payload) == []
