"""Glossary unit tests."""

from __future__ import annotations

import glossary


def test_glossary_has_required_terms():
    required = {
        "aeo_health",
        "entity_score",
        "ai_llm_visibility",
        "content_gap",
        "optimization_opportunity",
        "query_coverage",
        "evidence",
        "recommendation",
        "provenance",
    }
    assert required <= set(glossary.GLOSSARY)


def test_info_and_detail_text():
    info = glossary.info_text("aeo_health")
    assert "AEO Health" in info
    detail = glossary.detail_text("aeo_health")
    assert "health-v1" in detail
    assert "visibility" in detail.lower()


def test_guide_mentions_honesty():
    assert "final optimized page" in glossary.GUIDE_MARKDOWN.lower() or "final optimized" in glossary.GUIDE_MARKDOWN.lower()
    assert "same-host" in glossary.GUIDE_MARKDOWN.lower()
    md = glossary.all_terms_markdown()
    assert "Provenance" in md


def test_unknown_key_raises():
    try:
        glossary.get_entry("not_a_term")
        assert False, "expected KeyError"
    except KeyError:
        pass
