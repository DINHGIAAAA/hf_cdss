"""Tests for guideline PDF download URL resolution."""

from scraper.acquisition.download_sources import html_fallback_urls, pdf_download_candidates, resolve_guideline_pdf_url


def test_html_fallback_urls_includes_pubmed_for_med_link():
    urls = html_fallback_urls(
        {
            "html_url": "https://europepmc.org/article/MED/34709879",
            "notes": "Publisher blocks automated download.",
        }
    )
    assert urls[0].endswith("/34709879")
    assert any("pubmed.ncbi.nlm.nih.gov/34709879" in u for u in urls)


def test_pdf_download_candidates_orders_mirrors():
    urls = pdf_download_candidates("https://europepmc.org/articles/PMC8490362?pdf=render")
    assert urls[0].startswith("https://europepmc.org/")
    assert any("ebi.ac.uk/europepmc" in u for u in urls)
    assert any("ncbi.nlm.nih.gov" in u for u in urls)


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
