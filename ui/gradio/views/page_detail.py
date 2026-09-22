"""Page detail panel helpers."""

from __future__ import annotations

from typing import Any

from services.adapters import (
    adapt_before,
    adapt_evidence,
    adapt_recommendations,
    adapt_recommended_markdown,
    comparison_html,
    question_copy_payloads,
    question_opportunities_markdown,
    recommendations_markdown,
)


def render_page_detail(
    report: dict[str, Any],
    page_url: str | None,
    *,
    pages_payload: dict[str, Any] | None = None,
) -> dict[str, str]:
    before = adapt_before(report, page_url=page_url, pages_payload=pages_payload)
    recs = adapt_recommendations(report, page_url=page_url)
    recommended = adapt_recommended_markdown(report, page_url=page_url)
    evidence = adapt_evidence(report, page_url=page_url)
    q_md = question_opportunities_markdown(report, page_url=page_url)
    q_copy, o_copy, c_copy, per_q = question_copy_payloads(report, page_url=page_url)
    return {
        "before": before.markdown,
        "recommended_markdown": recommended,
        "why_these_changes": recommendations_markdown(recs),
        "evidence": evidence.markdown,
        "comparison_html": comparison_html(
            report, page_url, pages_payload=pages_payload
        ),
        "aeo_questions": q_md,
        "copy_questions": q_copy,
        "copy_opportunities": o_copy,
        "copy_recommended_changes": c_copy,
        "copy_per_question": per_q,
    }
