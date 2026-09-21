"""Page detail panel helpers."""

from __future__ import annotations

from typing import Any

from services.adapters import (
    adapt_before,
    adapt_brief,
    adapt_draft,
    adapt_evidence,
    adapt_recommendations,
    recommendations_markdown,
)


def render_page_detail(report: dict[str, Any], page_url: str | None) -> dict[str, str]:
    before = adapt_before(report, page_url=page_url)
    brief = adapt_brief(report, page_url=page_url)
    draft = adapt_draft(report, page_url=page_url)
    recs = adapt_recommendations(report, page_url=page_url)
    evidence = adapt_evidence(report, page_url=page_url)
    brief_md = brief.markdown if brief else "_No optimization brief for this page._"
    draft_md = (
        draft.body_markdown
        if draft
        else "_No content draft returned for this page._"
    )
    return {
        "before": before.markdown,
        "recommendations": recommendations_markdown(recs),
        "after": brief_md + "\n\n---\n\n" + draft_md,
        "evidence": evidence.markdown,
    }
