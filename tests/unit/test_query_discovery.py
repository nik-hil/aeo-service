"""Unit tests for query discovery."""

from __future__ import annotations

from aeo_mvp.queries.discovery import discover_queries, select_top_n, dedupe_queries, DiscoveredQuery
from aeo_mvp.understanding.site import SiteUnderstanding


def test_discover_queries_from_understanding():
    u = SiteUnderstanding(
        organization_brand="AcmeFlow",
        products_services=["Project Management Software"],
        topics=["What is a citable passage?", "AEO Basics"],
        audience_hints=["for teams"],
        industry_category_guess="project_management",
        site_genre="saas_product",
        commercial_intents=["pricing"],
        important_pages=[{"url": "https://demo.example/", "reasons": ["homepage"]}] * 6,
        structured={
            "primary_topics": {
                "evidence": [
                    {"evidence_class": "title_h1", "provenance": "observed"},
                    {"evidence_class": "article_body", "provenance": "observed"},
                ]
            },
            "org_name": {
                "evidence": [{"evidence_class": "og_meta", "provenance": "observed"}]
            },
            "products": {
                "evidence": [{"evidence_class": "jsonld", "provenance": "observed"}]
            },
            "site_genre": {
                "evidence": [{"evidence_class": "jsonld", "provenance": "observed"}]
            },
        },
        evidence_hash="legacy-acme",
    )
    result = discover_queries(u, top_n=10)
    assert result.fallback_used is False
    assert 8 <= result.selected_count <= 12
    classes = {q.classification for q in result.queries}
    assert "brand" in classes
    prompts = result.as_prompts()
    assert all("id" in p and "query" in p for p in prompts)


def test_fallback_when_empty():
    result = discover_queries(SiteUnderstanding(), top_n=10)
    assert result.fallback_used is True
    assert result.queries == []


def test_dedupe_and_select():
    cands = [
        DiscoveredQuery("a", "What is AcmeFlow?", "brand", "brand", score=1.0),
        DiscoveredQuery("b", "what is acmeflow?", "brand", "brand", score=0.9),
        DiscoveredQuery("c", "Alternatives to AcmeFlow", "alternatives", "alternatives", score=0.8),
    ]
    deduped = dedupe_queries(cands)
    assert len(deduped) == 2
    selected = select_top_n(deduped, top_n=8)
    assert len(selected) == 2
