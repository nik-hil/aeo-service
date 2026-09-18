"""Phase 5 pipeline: page_intel → gaps → brief → draft."""

from __future__ import annotations

from typing import Any

from aeo_mvp.content.brief import build_optimization_brief
from aeo_mvp.content.draft import build_optimized_draft, resolve_draft_generator
from aeo_mvp.content.gaps import build_content_gap_report
from aeo_mvp.content.models import ContentOptimizationResult, PageIntelligence
from aeo_mvp.content.page_intel import extract_page_intelligence


def run_content_optimization(
    *,
    html: str | None,
    url: str = "",
    title_hint: str | None = None,
    queryset: Any = None,
    site_profile: dict[str, Any] | None = None,
    config: dict[str, Any] | None = None,
    page_intelligence: PageIntelligence | None = None,
    generate_draft: bool = False,
    draft_paid: bool = False,
    llm_api_key: str | None = None,
    visibility_observations: list[dict[str, Any]] | None = None,
    source_excerpts: list[str] | None = None,
) -> ContentOptimizationResult:
    """Grounded optimization. Gaps+brief deterministic. Draft behind Protocol.

    Defaults: generate_draft=false, draft_paid=false, paid_retrieval=false.
    """
    cfg = dict(config or {})
    cfg.setdefault("generate_draft", generate_draft)
    cfg.setdefault("draft_paid", draft_paid)

    page = page_intelligence or extract_page_intelligence(
        html, url=url, title_hint=title_hint
    )
    gaps = build_content_gap_report(
        page,
        queryset,
        site_profile=site_profile,
        visibility_observations=visibility_observations,
    )
    brief = build_optimization_brief(
        page,
        gaps,
        site_profile=site_profile,
        queryset=queryset,
        config=cfg,
    )
    generator = resolve_draft_generator(
        generate_draft=bool(cfg.get("generate_draft", False)),
        draft_paid=bool(cfg.get("draft_paid", False)),
        api_key=llm_api_key,
        model=cfg.get("llm_model"),
    )
    draft = build_optimized_draft(
        page,
        brief,
        gaps,
        generator=generator,
        source_excerpts=source_excerpts,
    )
    return ContentOptimizationResult(
        page_intelligence=page,
        gap_report=gaps,
        brief=brief,
        draft=draft,
        paid_retrieval=False,
        paid_llm=bool(draft.paid_llm),
    )
