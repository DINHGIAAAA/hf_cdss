from scraper.transform.opendataloader_extract import parse_opendataloader_document
from scraper.transform.parse_guideline_pdf import split_sections


SAMPLE_DOCUMENT = {
    "file name": "ada_guideline.pdf",
    "number of pages": 2,
    "kids": [
        {
            "type": "heading",
            "page number": 1,
            "content": "4.1 Pharmacologic Treatment",
            "heading level": 2,
        },
        {
            "type": "paragraph",
            "page number": 1,
            "content": (
                "Abnormal kidney function results in alteration in pharmacokinetics "
                "and pharmacodynamics, and for people with CKD, as the GFR worsens, so does clearance."
            ),
        },
        {
            "type": "table",
            "page number": 1,
            "number of rows": 2,
            "number of columns": 2,
            "rows": [
                {
                    "type": "table row",
                    "row number": 1,
                    "cells": [
                        {"column number": 1, "kids": [{"type": "paragraph", "content": "Drug"}]},
                        {"column number": 2, "kids": [{"type": "paragraph", "content": "Dose"}]},
                    ],
                },
                {
                    "type": "table row",
                    "row number": 2,
                    "cells": [
                        {"column number": 1, "kids": [{"type": "paragraph", "content": "Metformin"}]},
                        {"column number": 2, "kids": [{"type": "paragraph", "content": "500 mg"}]},
                    ],
                },
            ],
        },
        {
            "type": "heading",
            "page number": 2,
            "content": "4.2 Monitoring",
            "heading level": 2,
        },
        {
            "type": "paragraph",
            "page number": 2,
            "content": "Monitor eGFR and electrolytes when indicated.",
        },
    ],
}


def test_parse_opendataloader_document_builds_pages_and_tables() -> None:
    pages, tables = parse_opendataloader_document(SAMPLE_DOCUMENT)

    assert len(pages) == 2
    assert pages[0]["page"] == 1
    assert "# 4.1 Pharmacologic Treatment" in pages[0]["text"]
    assert "pharmacokinetics" in pages[0]["text"]
    assert "TABLE" not in pages[0]["text"]

    assert len(tables) == 1
    assert tables[0]["page"] == 1
    assert tables[0]["rows"][0] == ["Drug", "Dose"]
    assert tables[0]["rows"][1] == ["Metformin", "500 mg"]


def test_split_sections_uses_opendataloader_heading_markers() -> None:
    pages, _ = parse_opendataloader_document(SAMPLE_DOCUMENT)
    sections = split_sections(pages)

    titles = [section["section"] for section in sections]
    assert "PHARMACOLOGIC TREATMENT" in titles
    assert "MONITORING" in titles
    assert any("pharmacokinetics" in section["text"] for section in sections)
