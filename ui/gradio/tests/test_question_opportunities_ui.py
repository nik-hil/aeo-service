"""Gradio adapter tests for AEO Questions & Opportunities."""

from __future__ import annotations

from services.adapters import (
    adapt_question_opportunities,
    error_question_opportunities_markdown,
    loading_question_opportunities_markdown,
    merge_page_opt_into_report,
    question_copy_payloads,
    question_opportunities_markdown,
)
from fixture_report import SAMPLE_REPORT


def test_merge_preserves_question_opportunity_analysis():
    opt = {
        "page_intelligence": {"url": "https://demo.example/about", "title": "About"},
        "question_opportunity_analysis": {
            "page_url": "https://demo.example/about",
            "status": "ok",
            "questions": [
                {
                    "question": "What is AcmeFlow?",
                    "answerability": "weak",
                    "importance": "medium",
                    "evidence": [],
                    "weakness": "thin",
                    "recommendation": "expand",
                    "grounding_status": "REQUIRES_NEW_INFORMATION",
                }
            ],
            "methodology": "question-opportunity-v1",
            "provider": "deterministic",
            "generated_at": "2026-01-01T00:00:00Z",
            "analysis_version": "question-opportunity-v1",
        },
    }
    merged = merge_page_opt_into_report(SAMPLE_REPORT, opt)
    assert merged["question_opportunity_analysis"]["questions"][0]["question"] == "What is AcmeFlow?"
    # Existing keys untouched
    assert merged["recommendations"]
    assert merged["scores"]


def test_adapt_unavailable_and_markdown():
    raw = adapt_question_opportunities({}, page_url="https://x")
    assert raw["status"] == "unavailable"
    md = question_opportunities_markdown(
        {
            "question_opportunity_analysis": {
                "status": "ok",
                "page_url": "https://demo.example/",
                "questions": [
                    {
                        "question": "What is AcmeFlow?",
                        "answerability": "strong",
                        "importance": "low",
                        "evidence": ["AcmeFlow helps teams."],
                        "evidence_location": "paragraph:1",
                        "weakness": "packaging",
                        "recommendation": "FAQ",
                        "grounding_status": "SAFE_TO_GENERATE",
                        "proposed_change": "**Q:** What is AcmeFlow?\n\nAcmeFlow helps teams.\n",
                    }
                ],
                "provider": "deterministic",
                "model": None,
                "generated_at": "2026-01-01T00:00:00Z",
                "analysis_version": "question-opportunity-v1",
            }
        },
        page_url="https://demo.example/",
    )
    assert "AEO QUESTIONS & OPPORTUNITIES" in md
    assert "What is AcmeFlow?" in md
    assert "Answerability" in md
    assert "Proposed change" in md

    cq, co, cc, per = question_copy_payloads(
        {
            "question_opportunity_analysis": {
                "status": "ok",
                "questions": [
                    {
                        "question": "What is AcmeFlow?",
                        "answerability": "weak",
                        "importance": "high",
                        "evidence": [],
                        "weakness": "thin",
                        "recommendation": "expand",
                        "grounding_status": "REQUIRES_NEW_INFORMATION",
                    }
                ],
            }
        },
        page_url="https://demo.example/",
    )
    assert "What is AcmeFlow?" in cq
    assert "Answerability: weak" in co
    assert cc == "" or "SAFE_TO_GENERATE" not in cc
    assert len(per) == 1
    assert "Grounding:" in per[0]


def test_loading_and_error_copy():
    assert "Analyzing AEO questions" in loading_question_opportunities_markdown()
    err = error_question_opportunities_markdown("timeout")
    assert "AEO question analysis unavailable" in err
    assert "timeout" in err
