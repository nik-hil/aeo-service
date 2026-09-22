"""Hashnode platform applicability + recommended Markdown generator."""

from __future__ import annotations

from aeo_mvp.platform.hashnode.applicability import (
    HASHNODE_PLATFORM_MANAGED_CODES,
    apply_hashnode_recommendation_filter,
    categorize_recommendation,
    is_hashnode_markdown_context,
)
from aeo_mvp.platform.hashnode.markdown_generator import generate_recommended_markdown


SAMPLE_MD = """# Agents Zero to Hero

Build an AI agent from scratch with tool calling.

## Why tools matter

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


def test_filter_suppresses_jsonld_meta_canonical_robots():
    recs = [
        {"code": "REC_ADD_JSONLD_ORG", "title": "Add JSON-LD"},
        {"code": "REC_ADD_META_DESCRIPTION", "title": "Meta"},
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
    assert "REC_ADD_META_DESCRIPTION" not in codes
    assert "REC_ADD_CANONICAL" not in codes
    assert "REC_FIX_ROBOTS_BLOCK" not in codes
    assert "REC_ADD_ANSWER_FIRST" in codes
    assert "REC_ADD_FAQ_SECTION" in codes
    # Remap content advice to Hashnode editor language.
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
        "REC_ADD_META_DESCRIPTION",
        "REC_ADD_CANONICAL",
        "REC_FIX_ROBOTS_BLOCK",
    ):
        assert code in HASHNODE_PLATFORM_MANAGED_CODES
        assert categorize_recommendation(code).value == "platform_managed"


def test_recommended_markdown_preserves_content_and_label():
    result = generate_recommended_markdown(
        source_markdown=SAMPLE_MD,
        page_intelligence={"title": "Agents Zero to Hero", "word_count": 40},
        brief={"proposed_title": "Agents Zero to Hero"},
        gaps=[],
        recommendations=[{"code": "REC_ADD_FAQ_SECTION"}],
    )
    assert result.ok
    assert "RECOMMENDED MARKDOWN" in result.body
    assert "guaranteed" not in result.body.lower() or "not a final or guaranteed" in result.body.lower()
    assert "final or guaranteed" in result.body.lower()
    assert "Agents Zero to Hero" in result.body
    assert "tool calling" in result.body
    assert "application/ld+json" not in result.body
    assert "<meta" not in result.body
    assert "```" not in result.body or result.body.count("```") % 2 == 0


def test_recommended_markdown_no_source_does_not_fabricate():
    result = generate_recommended_markdown(source_markdown=None)
    assert not result.ok
    assert "cannot be generated" in result.body.lower() or "no source" in result.body.lower()
    assert "RECOMMENDED MARKDOWN" in result.body
