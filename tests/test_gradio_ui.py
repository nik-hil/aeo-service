"""Focused Gradio UI formatting tests (no live LLM / Gradio launch)."""

from __future__ import annotations

from types import SimpleNamespace

import app as gradio_app


def _obs(**kwargs):
    defaults = dict(
        query="q",
        answer="answer text",
        mentioned=True,
        cited=False,
        target_domain_in_sources=True,
        target_page_in_sources=True,
        target_page_cited=False,
        source_urls=["https://example.com/a"],
        error=None,
    )
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


def _report(**overrides):
    visibility = SimpleNamespace(
        provider="digitalocean_web_search",
        model="m",
        notes="OBSERVED",
        mention_rate=0.5,
        citation_rate=0.25,
        target_in_sources_rate=0.5,
        target_page_in_sources_rate=0.4,
        target_page_citation_rate=0.2,
        observations=[_obs()],
    )
    base = SimpleNamespace(
        article=SimpleNamespace(
            title="T",
            section_headings=["H1"],
            target_domain="example.com",
            target_url="https://example.com/a",
            intro="intro",
        ),
        queries=SimpleNamespace(
            selected=[
                SimpleNamespace(
                    text="Why?",
                    importance="high",
                    reason="r",
                    article_topics_or_evidence="ev",
                )
            ],
            candidates=[1, 2, 3],
            quality_notes="ok",
        ),
        visibility=visibility,
        recommendations=SimpleNamespace(
            opportunities=[
                SimpleNamespace(
                    question="Why agents?",
                    gap="Missing loop explanation",
                    target_heading="What is an agent loop?",
                    recommended_change="Clarify the control flow.",
                    evidence_quote="The agent loop is the control flow",
                    answerability="weak",
                    source="llm_generated",
                )
            ],
            validation_warnings=[],
            change_explanations=["e1"],
            section_edits=[SimpleNamespace(target_heading="H")],
            source="llm_generated",
        ),
        quality_eval=SimpleNamespace(
            passed=True,
            summary="Looks good",
            question_feedback=[],
            recommendation_feedback=[],
            unsupported_claims=[],
            unnecessary_changes=[],
            explanations=[],
        ),
        current_markdown="# cur",
        recommended_markdown="# rec",
        diff="--- a\n+++ b\n@@\n-old\n+new\n",
        model="gpt",
        llm_used=True,
        retrieval_used=False,
        auto_publish=False,
    )
    for k, v in overrides.items():
        setattr(base, k, v)
    return base


def test_summary_includes_exact_page_metrics():
    html = gradio_app._summary_html(_report())
    assert "Exact Page" in html
    assert "Exact Citation" in html
    assert "40%" in html
    assert "20%" in html
    assert "PASS" in html


def test_visibility_cards_include_pr50_rates():
    html = gradio_app._visibility_html(_report())
    assert "Exact Page" in html
    assert "Exact Citation" in html
    assert "40%" in html
    assert "20%" in html
    assert "1 / 1 queries successfully observed" in html


def test_query_details_include_page_flags():
    md = gradio_app._query_details_md(_report())
    assert "target_page_in_sources: yes" in md
    assert "target_page_cited: no" in md


def test_opportunities_empty_state():
    r = _report()
    r.recommendations.opportunities = []
    html = gradio_app._opportunities_html(r)
    assert "No material opportunities found." in html


def test_opportunities_card_not_raw_json():
    html = gradio_app._opportunities_html(_report())
    assert "Why agents?" in html
    assert "CLARITY GAP" in html
    assert "llm_generated" not in html
    assert "Grounded" in html


def test_analyze_empty_markdown_single_error():
    outs = gradio_app.analyze("", "", True, False)
    assert "Analysis failed" in outs[0]
    assert "Provide Hashnode Markdown." in outs[0]
    # summary and other primary sections stay empty
    assert outs[1] == ""
    assert outs[2] == ""
    assert outs[5] == ""
