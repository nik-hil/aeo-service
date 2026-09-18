"""Stage 5.3 — OptimizedContentDraft from source page + brief."""

from __future__ import annotations

from aeo_mvp.optimization.change_plan import build_change_plan
from aeo_mvp.optimization.llm import ContentDraftWriter, HeuristicDraftWriter
from aeo_mvp.optimization.models import (
    DRAFT_VERSION,
    ContentGapReport,
    ContentOptimizationBrief,
    OptimizedContentDraft,
    PageIntelligence,
)


def build_optimized_draft(
    page: PageIntelligence,
    brief: ContentOptimizationBrief,
    gap_report: ContentGapReport,
    *,
    writer: ContentDraftWriter | None = None,
    source_excerpts: list[str] | None = None,
) -> OptimizedContentDraft:
    """Build optimized-content-v1. Default writer is heuristic (paid_llm=false)."""
    w = writer or HeuristicDraftWriter()
    result = w.write(page, brief, source_excerpts=source_excerpts)
    plan = build_change_plan(page, brief, gap_report)

    change_summary: list[str] = []
    for item in plan:
        change_summary.append(f"{item.action}: {item.target} — {item.reason}")

    return OptimizedContentDraft(
        schema_version=DRAFT_VERSION,
        page_url=page.url,
        title=result.title,
        meta_description=result.meta_description,
        body_markdown=result.body_markdown,
        faq=result.faq,
        schema_jsonld=result.schema_jsonld,
        internal_links=list(brief.internal_link_suggestions),
        change_summary=change_summary,
        change_plan=plan,
        unsupported_claim_warnings=list(result.unsupported_claim_warnings),
        writer=result.writer,
        llm_used=result.llm_used,
        paid_llm=result.paid_llm,
        method=f"{DRAFT_VERSION}+{result.writer}",
        warnings=list(result.warnings),
    )
