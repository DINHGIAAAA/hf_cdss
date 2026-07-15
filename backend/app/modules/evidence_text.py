"""Evidence text normalization for retrieval / display.

Delegates PDF flow repair to the scraper helpers so ingestion and runtime stay aligned.
"""

from __future__ import annotations

try:
    from scraper.transform.text_normalization import repair_pdf_flow_text
except ImportError:  # pragma: no cover - backend-only environments without scraper path
    import re
    import unicodedata

    def repair_pdf_flow_text(value: str | None) -> str:
        text = unicodedata.normalize("NFKC", value or "")
        text = text.replace("\xa0", " ")
        text = re.sub(r"[ \t]+", " ", text)
        return text.strip()


def normalize_evidence_text(value: str | None) -> str:
    return repair_pdf_flow_text(value)
