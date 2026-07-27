"""Tests for guideline PDF download URL resolution."""

from scraper.acquisition.download_sources import resolve_guideline_pdf_url


def test_pmc_landing_page_maps_to_europepmc_render():
    url = resolve_guideline_pdf_url(
        {
            "source_type": "guideline_pdf",
            "url": "https://pmc.ncbi.nlm.nih.gov/articles/PMC8490362/",
        }
    )
    assert url == "https://europepmc.org/articles/PMC8490362?pdf=render"


def test_explicit_pdf_url_wins():
    url = resolve_guideline_pdf_url(
        {
            "url": "https://pmc.ncbi.nlm.nih.gov/articles/PMC8490362/",
            "pdf_url": "https://example.com/custom.pdf",
        }
    )
    assert url == "https://example.com/custom.pdf"
