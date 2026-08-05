"""Tests for governance catalog filter facets API."""

from app.modules.governance.catalog_filter_facets import list_catalog_filter_facets


def test_unknown_catalog_returns_empty() -> None:
    assert list_catalog_filter_facets("not-a-catalog", {}) == {}
