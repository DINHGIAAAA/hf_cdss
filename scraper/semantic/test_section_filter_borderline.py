from scraper.semantic.section_filter import (
    SemanticProbe,
    is_borderline_score,
    review_borderline_section_with_llm,
    filter_important_sections,
)
from scraper.semantic import config


def test_is_borderline_score_window(monkeypatch):
    monkeypatch.setattr(config, "SECTION_BORDERLINE_LOW_THRESHOLD", 0.40)
    monkeypatch.setattr(config, "SECTION_SIMILARITY_THRESHOLD", 0.52)
    assert is_borderline_score(0.40)
    assert is_borderline_score(0.51)
    assert not is_borderline_score(0.39)
    assert not is_borderline_score(0.52)
    assert not is_borderline_score(0.70)


def test_review_borderline_keeps_valid_topic(monkeypatch):
    monkeypatch.setattr(
        "scraper.semantic.section_filter.call_llm_json",
        lambda *args, **kwargs: {"keep": True, "topic": "dosing", "confidence": 0.8},
    )
    topics = review_borderline_section_with_llm(
        {
            "source_type": "guideline",
            "section": "Titration notes",
            "text": "Start low and titrate beta blocker every 2 weeks.",
        },
        probe=SemanticProbe(best_score=0.45, best_topic="dosing"),
    )
    assert topics == ["dosing"]


def test_review_borderline_drops_when_llm_says_no(monkeypatch):
    monkeypatch.setattr(
        "scraper.semantic.section_filter.call_llm_json",
        lambda *args, **kwargs: {"keep": False, "topic": "", "confidence": 0.9},
    )
    topics = review_borderline_section_with_llm(
        {"source_type": "guideline", "section": "References", "text": "1. Smith et al."},
        probe=SemanticProbe(best_score=0.44, best_topic="recommendations"),
    )
    assert topics == []


def test_filter_calls_llm_only_for_borderline(monkeypatch):
    calls = {"n": 0}

    def fake_llm(*args, **kwargs):
        calls["n"] += 1
        return {"keep": True, "topic": "warnings", "confidence": 0.7}

    monkeypatch.setattr(config, "SECTION_BORDERLINE_LLM_ENABLED", True)
    monkeypatch.setattr(config, "SECTION_BORDERLINE_LOW_THRESHOLD", 0.40)
    monkeypatch.setattr(config, "SECTION_SIMILARITY_THRESHOLD", 0.52)
    monkeypatch.setattr(config, "SECTION_BORDERLINE_LLM_MAX", 10)
    monkeypatch.setattr(config, "SECTION_LOW_SCORE_TEXT_RESCUE_ENABLED", False)
    monkeypatch.setattr("scraper.semantic.section_filter.llm_available", lambda: True)
    monkeypatch.setattr("scraper.semantic.section_filter.call_llm_json", fake_llm)
    monkeypatch.setattr(
        "scraper.semantic.section_filter.warmup_prototype_vectors",
        lambda *args, **kwargs: None,
    )

    def fake_guideline_probe(record):
        title = record.get("section")
        if title == "clear_keep":
            return SemanticProbe(matches=["dosing"], best_score=0.80, best_topic="dosing")
        if title == "borderline":
            return SemanticProbe(matches=[], best_score=0.45, best_topic="warnings")
        return SemanticProbe(matches=[], best_score=0.20, best_topic="recommendations")

    monkeypatch.setattr("scraper.semantic.section_filter._semantic_guideline_probe", fake_guideline_probe)
    monkeypatch.setattr("scraper.semantic.section_filter.guideline_matches", lambda record: [])
    monkeypatch.setattr("scraper.semantic.section_filter.drug_matches", lambda record: [])
    monkeypatch.setattr(
        "scraper.semantic.section_filter.is_extracted_table_section",
        lambda record: False,
    )

    records = [
        {"source_type": "guideline", "section": "clear_keep", "text": "dose titration"},
        {"source_type": "guideline", "section": "borderline", "text": "caution with hyperkalemia"},
        {"source_type": "guideline", "section": "clear_drop", "text": "author affiliations"},
    ]
    kept = filter_important_sections(records)
    titles = {r["section"] for r in kept}
    assert "clear_keep" in titles
    assert "borderline" in titles
    assert "clear_drop" not in titles
    assert calls["n"] == 1
    borderline = next(r for r in kept if r["section"] == "borderline")
    assert borderline["metadata"]["section_match_method"] == "borderline_llm"


def test_borderline_llm_prioritizes_higher_scores(monkeypatch):
    seen_scores: list[float] = []

    def fake_llm(system, user, **kwargs):
        import json

        payload = json.loads(user)
        seen_scores.append(payload["embed_best_score"])
        return {"keep": False, "topic": "", "confidence": 0.5}

    monkeypatch.setattr(config, "SECTION_BORDERLINE_LLM_ENABLED", True)
    monkeypatch.setattr(config, "SECTION_BORDERLINE_LOW_THRESHOLD", 0.40)
    monkeypatch.setattr(config, "SECTION_SIMILARITY_THRESHOLD", 0.52)
    monkeypatch.setattr(config, "SECTION_BORDERLINE_LLM_MAX", 1)
    monkeypatch.setattr(config, "SECTION_LOW_SCORE_TEXT_RESCUE_ENABLED", False)
    monkeypatch.setattr("scraper.semantic.section_filter.llm_available", lambda: True)
    monkeypatch.setattr("scraper.semantic.section_filter.call_llm_json", fake_llm)
    monkeypatch.setattr(
        "scraper.semantic.section_filter.warmup_prototype_vectors",
        lambda *args, **kwargs: None,
    )
    monkeypatch.setattr("scraper.semantic.section_filter.guideline_matches", lambda record: [])
    monkeypatch.setattr(
        "scraper.semantic.section_filter.is_extracted_table_section",
        lambda record: False,
    )

    def fake_probe(record):
        score = float(record["score"])
        return SemanticProbe(matches=[], best_score=score, best_topic="dosing")

    monkeypatch.setattr("scraper.semantic.section_filter._semantic_guideline_probe", fake_probe)

    records = [
        {"source_type": "guideline", "section": "low_border", "text": "x", "score": "0.41"},
        {"source_type": "guideline", "section": "high_border", "text": "y", "score": "0.50"},
    ]
    filter_important_sections(records)
    assert seen_scores == [0.5]


def test_low_score_text_rescue(monkeypatch):
    from scraper.semantic.section_filter import low_score_text_rescue_matches

    monkeypatch.setattr(config, "SECTION_LOW_SCORE_TEXT_RESCUE_ENABLED", True)
    hits = low_score_text_rescue_matches(
        {
            "section": "Misc notes",
            "text": "The starting dose is 25 mg once daily; titrate every 2 weeks.",
        }
    )
    assert "dosing" in hits

    monkeypatch.setattr(config, "SECTION_BORDERLINE_LLM_ENABLED", False)
    monkeypatch.setattr(config, "SECTION_BORDERLINE_LOW_THRESHOLD", 0.40)
    monkeypatch.setattr(config, "SECTION_SIMILARITY_THRESHOLD", 0.52)
    monkeypatch.setattr(
        "scraper.semantic.section_filter.warmup_prototype_vectors",
        lambda *args, **kwargs: None,
    )
    monkeypatch.setattr("scraper.semantic.section_filter.guideline_matches", lambda record: [])
    monkeypatch.setattr(
        "scraper.semantic.section_filter.is_extracted_table_section",
        lambda record: False,
    )
    monkeypatch.setattr(
        "scraper.semantic.section_filter._semantic_guideline_probe",
        lambda record: SemanticProbe(matches=[], best_score=0.22, best_topic="dosing"),
    )
    kept = filter_important_sections(
        [
            {
                "source_type": "guideline",
                "section": "Misc notes",
                "text": "The starting dose is 25 mg once daily; titrate every 2 weeks.",
            }
        ]
    )
    assert len(kept) == 1
    assert kept[0]["metadata"]["section_match_method"] == "low_score_text_rescue"
