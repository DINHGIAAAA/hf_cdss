import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scraper.semantic.section_filter import filter_important_sections
from scraper.transform.table_sections import (
    build_table_section_records,
    is_extracted_table_section,
    rows_to_markdown,
)


def test_rows_to_markdown_renders_pipe_table() -> None:
    markdown = rows_to_markdown(
        [
            ["Drug", "Dose"],
            ["Metformin", "500 mg"],
        ]
    )

    assert markdown.splitlines() == [
        "| Drug | Dose |",
        "| --- | --- |",
        "| Metformin | 500 mg |",
    ]


def test_build_table_section_records_produces_markdown_sections() -> None:
    provenance = {
        "source_id": "ada_guideline",
        "source_url": "https://example.test/ada",
    }
    tables, sections = build_table_section_records(
        [{"page": 4, "table_index": 3, "rows": [["eGFR", "Action"], ["<30", "Avoid MRA"]]}],
        document_id="ada_guideline",
        provenance=provenance,
        guideline_topic="diabetes",
        source_file="raw/guidelines/diabetes/ada.pdf",
    )

    assert len(tables) == 1
    assert len(sections) == 1
    assert sections[0]["section"] == "TABLE 3"
    assert "| eGFR | Action |" in sections[0]["text"]
    assert sections[0]["metadata"]["content_type"] == "extracted_table"


def test_extracted_table_sections_always_pass_important_filter(monkeypatch) -> None:
    from scraper.semantic.embeddings import clear_embedding_caches

    clear_embedding_caches()
    monkeypatch.setattr(
        "scraper.semantic.embeddings.embed_texts",
        lambda texts, **kwargs: [[1.0, 0.0] for _ in texts],
    )

    record = {
        "document_id": "esc_hf",
        "source_type": "guideline",
        "section": "TABLE 1",
        "text": "| Class | Recommendation |\n| --- | --- |\n| I | Start GDMT |",
        "metadata": {"content_type": "extracted_table", "table_index": 1, "page": 2},
    }

    assert is_extracted_table_section(record) is True
    important = filter_important_sections([record])
    assert len(important) == 1
    assert important[0]["metadata"]["section_match_method"] == "extracted_table"
