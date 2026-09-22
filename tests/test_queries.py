"""Tests for article-specific query discovery."""

from aeo_mvp.article import load_hashnode_markdown
from aeo_mvp.queries import discover_queries

ARTICLE = """# Shipping Fast APIs with FastAPI

FastAPI is a Python web framework for building APIs quickly with type hints.

## Request validation

Pydantic models validate request bodies before your route runs.

## Dependency injection

Dependencies let you share database sessions and auth checks across routes.

## Performance tips

Use async routes for I/O and avoid blocking calls in the event loop.

## Comparison with Flask

Flask is simpler for tiny apps; FastAPI adds validation and OpenAPI by default.
"""


def test_queries_are_article_specific_not_universal_list():
    article = load_hashnode_markdown(text=ARTICLE)
    qs = discover_queries(article, top_n=18)
    assert 15 <= len(qs.selected) <= 20 or 8 <= len(qs.selected) <= 25
    assert 20 <= len(qs.candidates) <= 30 or len(qs.candidates) >= 15
    joined = " ".join(q.text.lower() for q in qs.selected)
    # Must reflect this article's topics — not a fixed global SEO list.
    assert "fastapi" in joined or "validation" in joined or "flask" in joined
    assert "best seo tools 2024" not in joined


def test_query_coverage_across_sections():
    article = load_hashnode_markdown(text=ARTICLE)
    qs = discover_queries(article, top_n=18)
    sources = {q.source_section for q in qs.selected if q.source_section}
    # At least two distinct body sections represented.
    assert len(sources) >= 2
