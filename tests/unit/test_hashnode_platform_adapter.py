"""Hashnode platform applicability + recommended Markdown generator."""

from __future__ import annotations

from types import SimpleNamespace

from aeo_mvp.platform.hashnode.applicability import (
    HASHNODE_PLATFORM_MANAGED_CODES,
    RecommendationCategory,
    apply_hashnode_recommendation_filter,
    categorize_recommendation,
    filter_recommendations_page_scoped,
    is_hashnode_markdown_context,
)
from aeo_mvp.platform.hashnode.markdown_generator import (
    SUGGESTED_MARKDOWN_SUBTITLE,
    generate_recommended_markdown,
)


SAMPLE_MD = """# Agents Zero to Hero

Build an AI agent from scratch with tool calling.

## Why tools matter

Permissions and careful tool design keep agents useful.
"""

SAMPLE_WITH_QA = """# Agents Zero to Hero

Build an AI agent from scratch with tool calling.

## What is an AI agent?

An AI agent is software that plans and uses tools to complete a goal.

## Why do tools matter?

Permissions and careful tool design keep agents useful.
"""


def test_is_hashnode_markdown_context():
    assert is_hashnode_markdown_context(
        url="https://nik-hil.hashnode.dev/my-article",
        content_representation="markdown",
        source_url="https://nik-hil.hashnode.dev/my-article.md",
    )
    assert not is_hashnode_markdown_context(
        url="https://example.com/post",
        content_representation="markdown",
    )
    assert not is_hashnode_markdown_context(
        url="https://nik-hil.hashnode.dev/my-article",
        content_representation="html",
    )


def test_filter_keeps_seo_description_suppresses_platform_managed():
    """SEO description is user-editable on Hashnode; HTML/infra SEO is not."""
    recs = [
        {"code": "REC_ADD_JSONLD_ORG", "title": "Add JSON-LD"},
        {
            "code": "REC_ADD_META_DESCRIPTION",
            "title": "Add a meta description",
            "recommended_action": 'Add a <meta name="description"> tag.',
        },
        {"code": "REC_ADD_CANONICAL", "title": "Canonical"},
        {"code": "REC_FIX_ROBOTS_BLOCK", "title": "Robots"},
        {"code": "REC_ADD_ANSWER_FIRST", "title": "Answer first", "recommended_action": "x"},
        {"code": "REC_ADD_FAQ_SECTION", "title": "FAQ"},
    ]
    filtered = apply_hashnode_recommendation_filter(
        recs,
        url="https://nik-hil.hashnode.dev/my-article",
        content_representation="markdown",
        source_url="https://nik-hil.hashnode.dev/my-article.md",
    )
    codes = {r["code"] for r in filtered}
    assert "REC_ADD_JSONLD_ORG" not in codes
    assert "REC_ADD_CANONICAL" not in codes
    assert "REC_FIX_ROBOTS_BLOCK" not in codes
    assert "REC_ADD_META_DESCRIPTION" in codes
    assert "REC_ADD_ANSWER_FIRST" in codes
    assert "REC_ADD_FAQ_SECTION" in codes

    seo = next(r for r in filtered if r["code"] == "REC_ADD_META_DESCRIPTION")
    assert seo["applicability_category"] == RecommendationCategory.USER_EDITABLE.value
    assert "SEO description" in seo["title"] or "SEO description" in seo["recommended_action"]
    assert "Hashnode" in seo["recommended_action"]
    assert "SEO settings" in seo["recommended_action"]
    assert "<meta" not in seo["recommended_action"]
    assert "Add a <meta" not in seo["recommended_action"]
    assert 'name="description"' not in seo["recommended_action"]

    af = next(r for r in filtered if r["code"] == "REC_ADD_ANSWER_FIRST")
    assert "Hashnode" in af["recommended_action"]
    assert "<meta" not in af["recommended_action"]


def test_non_hashnode_filter_passthrough():
    recs = [{"code": "REC_ADD_JSONLD_ORG", "title": "Add JSON-LD"}]
    out = apply_hashnode_recommendation_filter(
        recs,
        url="https://example.com/",
        content_representation="html",
    )
    assert len(out) == 1


def test_platform_managed_codes_categorized():
    for code in (
        "REC_ADD_JSONLD_ORG",
        "REC_ADD_CANONICAL",
        "REC_FIX_ROBOTS_BLOCK",
        "REC_REMOVE_NOINDEX",
    ):
        assert code in HASHNODE_PLATFORM_MANAGED_CODES
        assert categorize_recommendation(code).value == "platform_managed"
    assert "REC_ADD_META_DESCRIPTION" not in HASHNODE_PLATFORM_MANAGED_CODES
    assert (
        categorize_recommendation("REC_ADD_META_DESCRIPTION").value
        == RecommendationCategory.USER_EDITABLE.value
    )


def test_recommended_markdown_body_is_paste_ready_only():
    """P0: body has no disclaimer / RECOMMENDED MARKDOWN heading / placeholders / HTML SEO."""
    result = generate_recommended_markdown(
        source_markdown=SAMPLE_MD,
        page_intelligence={"title": "Agents Zero to Hero", "word_count": 40},
        brief={"proposed_title": "Agents Zero to Hero"},
        gaps=[],
        recommendations=[{"code": "REC_ADD_FAQ_SECTION"}],
        source_url="https://nik-hil.hashnode.dev/agents.md",
    )
    assert result.ok
    assert "RECOMMENDED MARKDOWN" not in result.body
    assert "Suggested Markdown draft" not in result.body
    assert SUGGESTED_MARKDOWN_SUBTITLE not in result.body
    assert "guaranteed" not in result.body.lower()
    assert "review before publishing" not in result.body.lower()
    assert "_Add a concise" not in result.body
    assert "_Describe the first concrete step" not in result.body
    assert "application/ld+json" not in result.body
    assert "<meta" not in result.body
    assert "<script" not in result.body
    assert "Agents Zero to Hero" in result.body
    assert "tool calling" in result.body
    assert "insufficient_evidence_faq" in result.warnings
    assert result.source_url.endswith("agents.md")
    assert result.generator_version


def test_recommended_markdown_no_source_does_not_fabricate():
    result = generate_recommended_markdown(source_markdown=None)
    assert not result.ok
    assert result.body == ""
    assert "no_source_markdown" in result.warnings
    assert "RECOMMENDED MARKDOWN" not in result.body


def test_recommended_markdown_no_safe_change_preserves_source():
    result = generate_recommended_markdown(
        source_markdown=SAMPLE_MD,
        recommendations=[],
        gaps=[],
    )
    assert result.ok
    assert result.body.strip() == SAMPLE_MD.strip()
    assert result.changed is False
    assert "RECOMMENDED MARKDOWN" not in result.body


def test_recommended_markdown_does_not_fabricate_faq_or_howto():
    result = generate_recommended_markdown(
        source_markdown=SAMPLE_MD,
        recommendations=[
            {"code": "REC_ADD_FAQ_SECTION"},
            {"code": "REC_ADD_HOWTO_OR_STEPS"},
        ],
    )
    assert "## FAQ" not in result.body
    assert "## Steps" not in result.body
    assert "_Add a concise" not in result.body
    assert "_Describe the" not in result.body
    assert "insufficient_evidence_faq" in result.warnings
    assert "insufficient_evidence_howto" in result.warnings
    assert result.body.strip() == SAMPLE_MD.strip()


def test_recommended_markdown_evidence_backed_faq_can_improve():
    result = generate_recommended_markdown(
        source_markdown=SAMPLE_WITH_QA,
        recommendations=[{"code": "REC_ADD_FAQ_SECTION"}],
    )
    assert result.ok
    assert result.changed is True
    assert "## FAQ" in result.body
    assert "What is an AI agent?" in result.body
    assert "An AI agent is software" in result.body
    assert "_Add a concise" not in result.body
    assert "RECOMMENDED MARKDOWN" not in result.body


def test_page_scoped_filter_only_affects_hashnode_md_recs():
    """Multi-page crawl: Hashnode filter only on Hashnode MD page; HTML unchanged."""
    hashnode_url = "https://nik-hil.hashnode.dev/my-article"
    html_url = "https://example.com/about"
    pages = [
        SimpleNamespace(
            url=hashnode_url,
            content_representation="markdown",
            source_url=f"{hashnode_url}.md",
        ),
        SimpleNamespace(
            url=html_url,
            content_representation="html",
            source_url=None,
        ),
    ]
    recs = [
        {
            "code": "REC_ADD_JSONLD_ORG",
            "title": "Add JSON-LD",
            "affected_urls": [hashnode_url],
        },
        {
            "code": "REC_ADD_META_DESCRIPTION",
            "title": "Add a meta description",
            "recommended_action": 'Add a <meta name="description"> tag.',
            "affected_urls": [hashnode_url],
        },
        {
            "code": "REC_ADD_JSONLD_ORG",
            "title": "Add JSON-LD on HTML",
            "affected_urls": [html_url],
            "recommended_action": "Add Organization JSON-LD",
        },
        {
            "code": "REC_ADD_CANONICAL",
            "title": "Canonical on HTML",
            "affected_urls": [html_url],
        },
        {
            "code": "REC_FIX_HOME_HTTP",
            "title": "Site-level HTTP",
            "affected_urls": [],
        },
    ]
    out = filter_recommendations_page_scoped(recs, pages)
    codes_by_url: dict[str, set[str]] = {}
    site_level = []
    for r in out:
        urls = r.get("affected_urls") or []
        if not urls:
            site_level.append(r["code"])
            continue
        for u in urls:
            codes_by_url.setdefault(u, set()).add(r["code"])

    # Hashnode MD: platform-managed JSON-LD suppressed; SEO description remapped.
    assert "REC_ADD_JSONLD_ORG" not in codes_by_url.get(hashnode_url, set())
    assert "REC_ADD_META_DESCRIPTION" in codes_by_url.get(hashnode_url, set())
    seo = next(
        r
        for r in out
        if r["code"] == "REC_ADD_META_DESCRIPTION"
        and hashnode_url in (r.get("affected_urls") or [])
    )
    assert "SEO settings" in seo["recommended_action"]
    assert "<meta" not in seo["recommended_action"]

    # HTML page: generic recs unchanged (JSON-LD + canonical still present).
    assert "REC_ADD_JSONLD_ORG" in codes_by_url.get(html_url, set())
    assert "REC_ADD_CANONICAL" in codes_by_url.get(html_url, set())
    html_jsonld = next(
        r
        for r in out
        if r["code"] == "REC_ADD_JSONLD_ORG" and html_url in (r.get("affected_urls") or [])
    )
    assert html_jsonld["title"] == "Add JSON-LD on HTML"
    assert "applicability_category" not in html_jsonld

    # Site-level left alone even though a Hashnode MD page exists.
    assert "REC_FIX_HOME_HTTP" in site_level
