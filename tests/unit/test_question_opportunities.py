"""Unit tests for AEO Questions & Opportunities analysis."""

from __future__ import annotations

import pytest

from aeo_mvp.content.grounded_synth import (
    evidence_quote_in_article,
    synthesize_proposed_change,
    validate_evidence_list,
    ws_canonical,
)
from aeo_mvp.content.models import PageIntelligence, HeadingNode
from aeo_mvp.content.pipeline import run_content_optimization
from aeo_mvp.content.question_opportunities import (
    TARGET_QUESTION_COUNT,
    build_question_opportunity_analysis,
    classify_answerability,
    copy_text_one_question,
    copy_text_opportunities,
    copy_text_questions,
    copy_text_recommended_changes,
    parse_llm_question_json,
    validate_and_ground_llm_items,
)


ARTICLE = """
# Agents Zero to Hero #1: Building an AI Agent from Scratch with Tool Calling

An AI agent is a system that uses a language model to decide when to call tools
and how to combine the results toward completing a user task.

## Tool calling basics

Tool calling lets the model invoke functions such as search or code execution.
The agent loop continues until the task is complete.

## Why it matters

Building agents from scratch teaches the control flow behind popular frameworks.
You learn how prompts, tools, and observation steps fit together.

Paragraph with enough substance for evidence matching across multiple sentences
about AI agents and tool calling in practical tutorials.
"""


def _page() -> PageIntelligence:
    return PageIntelligence(
        url="https://nik-hil.hashnode.dev/agents-zero-to-hero-1-building-an-ai-agent-from-scratch-with-tool-calling",
        title="Agents Zero to Hero #1: Building an AI Agent from Scratch with Tool Calling",
        h1="Agents Zero to Hero #1: Building an AI Agent from Scratch with Tool Calling",
        headings=[
            HeadingNode(level=1, text="Agents Zero to Hero #1: Building an AI Agent from Scratch with Tool Calling"),
            HeadingNode(level=2, text="Tool calling basics"),
            HeadingNode(level=2, text="Why it matters"),
        ],
        topics=["ai", "agent", "tool", "calling"],
        word_count=120,
        faq_coverage={
            "has_faq_schema": False,
            "question_headings": ["What is tool calling?"],
            "question_count": 1,
        },
    )


def test_ws_canonical_and_evidence_validation():
    assert ws_canonical("  Hello\nWorld  ") == "hello world"
    assert evidence_quote_in_article(
        "An AI agent is a system that uses a language model",
        ARTICLE,
    )
    assert not evidence_quote_in_article(
        "Completely invented statistic 99.9% never seen",
        ARTICLE,
    )
    kept, rejected = validate_evidence_list(
        [
            "Tool calling lets the model invoke functions such as search or code execution.",
            "Invented claim about 500% growth",
        ],
        ARTICLE,
    )
    assert len(kept) == 1
    assert len(rejected) == 1


def test_classify_answerability():
    strong_ev = [
        "An AI agent is a system that uses a language model to decide when to call tools "
        "and how to combine the results toward completing a user task."
    ]
    assert (
        classify_answerability(
            coverage="full",
            evidence=strong_ev,
            question="What is an AI agent?",
            article_text=ARTICLE,
        )
        == "strong"
    )
    assert (
        classify_answerability(
            coverage="absent",
            evidence=[],
            question="What is pricing for Acme?",
            article_text=ARTICLE,
        )
        == "missing"
    )


def test_grounded_synth_safe_and_requires_new_info():
    proposed, status, _warn = synthesize_proposed_change(
        question="What is an AI agent?",
        evidence=[
            "An AI agent is a system that uses a language model to decide when to call tools "
            "and how to combine the results toward completing a user task."
        ],
        article_text=ARTICLE,
        answerability="strong",
    )
    assert status == "SAFE_TO_GENERATE"
    assert proposed and "AI agent" in proposed

    proposed2, status2, _ = synthesize_proposed_change(
        question="What is the price?",
        evidence=["Invented 42% conversion rate boost"],
        article_text=ARTICLE,
        answerability="weak",
    )
    assert proposed2 is None
    assert status2 in ("REQUIRES_NEW_INFORMATION", "REJECTED_UNGROUNDED")


def test_parse_llm_json_ok_and_malformed():
    raw = {
        "questions": [
            {
                "question": "What is an AI agent?",
                "answerability": "strong",
                "evidence": [
                    "An AI agent is a system that uses a language model to decide when to call tools "
                    "and how to combine the results toward completing a user task."
                ],
            }
        ]
    }
    items = parse_llm_question_json(raw)
    assert len(items) == 1
    with pytest.raises(ValueError, match="malformed_llm_json"):
        parse_llm_question_json("{not json")
    with pytest.raises(ValueError, match="llm_json_missing_questions_array"):
        parse_llm_question_json({"nope": []})


def test_llm_invented_claims_rejected():
    items = parse_llm_question_json(
        {
            "questions": [
                {
                    "question": "What is an AI agent?",
                    "answerability": "strong",
                    "evidence": ["Totally fabricated evidence about 900% ROI"],
                    "proposed_change": "Add claim: 900% ROI guaranteed.",
                }
            ]
        }
    )
    qs, warnings = validate_and_ground_llm_items(items, article_text=ARTICLE)
    assert qs[0].answerability == "missing"
    assert qs[0].proposed_change is None
    assert qs[0].grounding_status == "REQUIRES_NEW_INFORMATION"
    assert any("llm_evidence_rejected" in w for w in warnings)


def test_build_analysis_produces_about_ten_questions():
    page = _page()
    queryset = {
        "members": [
            {"query": {"query_id": "q1", "text": "What is an AI agent?"}},
            {"query": {"query_id": "q2", "text": "How does tool calling work?"}},
            {"query": {"query_id": "q3", "text": "Why build agents from scratch?"}},
            {"query": {"query_id": "q4", "text": "How do I get started with AI agents?"}},
            {"query": {"query_id": "q5", "text": "What is Agents Zero to Hero?"}},
        ],
        "query_set_version": "query-set-v3",
    }
    analysis = build_question_opportunity_analysis(
        page,
        article_text=ARTICLE,
        queryset=queryset,
        visibility_observations=[
            {
                "query_id": "q1",
                "detected_mention": True,
                "detected_citation": False,
                "search_queries": ["ai agent tool calling"],
            }
        ],
    )
    assert analysis.status == "ok"
    assert 8 <= len(analysis.questions) <= TARGET_QUESTION_COUNT
    assert analysis.provider == "deterministic"
    assert analysis.analysis_version
    assert analysis.generated_at
    # At least one related search signal when obs available
    assert any(q.related_search_observations for q in analysis.questions)
    for q in analysis.questions:
        for ev in q.evidence:
            assert evidence_quote_in_article(ev, ARTICLE)
        if q.grounding_status == "SAFE_TO_GENERATE":
            assert q.proposed_change
        if q.answerability == "missing":
            assert q.proposed_change is None


def test_copy_text_builders():
    page = _page()
    analysis = build_question_opportunity_analysis(page, article_text=ARTICLE)
    qs = copy_text_questions(analysis)
    assert "?\n" in qs or qs.endswith("?")
    opps = copy_text_opportunities(analysis)
    # Opportunities omit strong-only rows; still plain text
    assert isinstance(opps, str)
    changes = copy_text_recommended_changes(analysis)
    if changes.strip():
        assert "Question:" in changes
    if analysis.questions:
        one = copy_text_one_question(analysis.questions[0])
        assert "Answerability:" in one
        assert "Grounding:" in one


def test_empty_article_no_invented_proposed_change():
    page = PageIntelligence(
        url="https://example.com/empty",
        title="Empty",
        word_count=0,
    )
    analysis = build_question_opportunity_analysis(page, article_text="")
    for q in analysis.questions:
        assert q.proposed_change is None or q.grounding_status != "SAFE_TO_GENERATE"


def test_pipeline_includes_question_opportunity_analysis():
    html = f"<html><body><article>{ARTICLE.replace(chr(10), '<br/>')}</article></body></html>"
    result = run_content_optimization(
        html=html,
        url="https://nik-hil.hashnode.dev/agents-zero-to-hero-1-building-an-ai-agent-from-scratch-with-tool-calling",
        title_hint="Agents Zero to Hero #1",
        queryset={
            "members": [
                {"query": {"query_id": "q1", "text": "What is an AI agent?"}},
                {"query": {"query_id": "q2", "text": "How does tool calling work?"}},
            ]
        },
        source_markdown=ARTICLE,
    )
    wire = result.to_dict()
    assert "question_opportunity_analysis" in wire
    qoa = wire["question_opportunity_analysis"]
    assert qoa["status"] == "ok"
    assert len(qoa["questions"]) == TARGET_QUESTION_COUNT
    # Existing panels data still present
    assert wire["page_intelligence"]
    assert wire["content_gaps"]
    assert wire["optimization_briefs"]
    assert wire["content_drafts"]
