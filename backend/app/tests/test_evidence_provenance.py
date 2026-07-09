from app.modules.evidence_text import normalize_evidence_text
from app.modules.graphrag import service as graphrag_service


def test_normalize_evidence_text_repairs_common_mojibake() -> None:
    raw = "ELIQUIS warnings: \u00e2\u20ac\u00a2 Active bleeding \u00e2\u20ac\u201c review."

    normalized = normalize_evidence_text(raw)

    assert "\u00e2\u20ac\u00a2" not in normalized
    assert "\u00e2\u20ac\u201c" not in normalized
    assert "- Active bleeding - review." in normalized


def test_local_evidence_retrieval_preserves_provenance_metadata(monkeypatch) -> None:
    monkeypatch.setattr(
        graphrag_service,
        "load_published_chunks",
        lambda: [
            {
                "chunk_id": "chunk_1",
                "document_id": "apixaban",
                "source_type": "drug_label",
                "section": "CONTRAINDICATIONS",
                "text": "ELIQUIS is contraindicated: \u00e2\u20ac\u00a2 Active pathological bleeding.",
                "metadata": {
                    "source_id": "apixaban_dailymed_label",
                    "source_url": "https://dailymed.nlm.nih.gov/example",
                    "publisher": "DailyMed",
                    "citation": "Apixaban DailyMed SPL. DailyMed.",
                    "page": None,
                    "provenance": {
                        "source_id": "apixaban_dailymed_label",
                        "section": "CONTRAINDICATIONS",
                        "setid": "abc",
                    },
                },
            }
        ],
    )
    monkeypatch.setattr(graphrag_service, "_fetch_chroma_candidates", lambda *_args, **_kwargs: [])

    def fake_bm25(terms, top_k, **kwargs):
        row = graphrag_service.load_published_chunks()[0]
        return [graphrag_service._evidence_chunk_from_row(row, score=1.0, terms=terms)]

    monkeypatch.setattr(graphrag_service, "retrieve_bm25_evidence_chunks", fake_bm25)
    monkeypatch.setattr(
        graphrag_service,
        "rerank_evidence_chunks",
        lambda _query, chunks, top_k: chunks[:top_k],
    )
    monkeypatch.setattr(
        graphrag_service,
        "filter_evidence_chunks",
        lambda chunks, **kwargs: chunks[: kwargs.get("top_k")],
    )

    chunks = graphrag_service.retrieve_evidence_chunks(["bleeding"], top_k=1)

    assert chunks[0].text == "ELIQUIS is contraindicated: - Active pathological bleeding."
    assert chunks[0].metadata["source_id"] == "apixaban_dailymed_label"
    assert chunks[0].metadata["provenance"]["section"] == "CONTRAINDICATIONS"

