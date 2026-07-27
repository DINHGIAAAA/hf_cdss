"""Smoke tests for scraper.semantic.config — verify all tunables are defined and sane."""

from scraper.semantic import config


def test_config_import_succeeds():
    """Importing the config module must not raise."""
    # If this passes, no NameError in module body.
    pass


def test_timeout_values_are_positive():
    assert config.LLM_TIMEOUT_SECONDS > 0
    assert config.CONDITION_REFINE_LLM_TIMEOUT_SECONDS >= config.LLM_TIMEOUT_SECONDS
    assert config.INGESTION_LLM_TIMEOUT_SECONDS >= config.LLM_TIMEOUT_SECONDS
    assert config.EMBEDDING_TIMEOUT_SECONDS > 0


def test_max_tokens_positive():
    assert config.LLM_MAX_TOKENS > 0
    assert config.CONDITION_REFINE_LLM_MAX_TOKENS > 0


def test_concurrency_at_least_one():
    assert config.LLM_CONCURRENCY >= 1
    assert config.EMBEDDING_BATCH_SIZE >= 1
    assert config.EMBEDDING_PARALLEL_WORKERS >= 1


def test_adaptive_threshold_enabled_sane_defaults():
    assert isinstance(config.SECTION_ADAPTIVE_THRESHOLD_ENABLED, bool)
    assert 0 < config.SECTION_SIMILARITY_THRESHOLD < 1.0
    assert 0 < config.SECTION_BORDERLINE_LOW_THRESHOLD < 1.0
    assert config.SECTION_BORDERLINE_LOW_THRESHOLD < config.SECTION_SIMILARITY_THRESHOLD


def test_condition_refine_max_tokens_reasonable(monkeypatch):
    """CONDITION_REFINE_LLM_MAX_TOKENS=250 must still allow multi-condition JSON."""
    assert config.CONDITION_REFINE_LLM_MAX_TOKENS <= 300, (
        "250 tokens is tight for multi-condition JSON; "
        "ensure callers handle truncation gracefully"
    )
