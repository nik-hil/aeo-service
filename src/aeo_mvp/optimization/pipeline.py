"""Phase 5 pipeline: intelligence → gaps → brief → draft."""

from __future__ import annotations

from typing import Any

from aeo_mvp.optimization.brief import build_optimization_brief
from aeo_mvp.optimization.draft import build_optimized_draft
from aeo_mvp.optimization.gaps import build_content_gap_report
from aeo_mvp.optimization.llm import resolve_writer
from aeo_mvp.optimization.models import ContentOptimizationResult, PageIntelligence
from aeo_mvp.optimization.page_intelligence import extract_page_intelligence


def run_content_optimization(
    *,
    html: str | None,
    url: str = "",
    title_hint: str | None = None,
    queryset: Any = None,
    site_profile: dict[str, Any] | None = None,
    config: dict[str, Any] | None = None,
    page_intelligence: PageIntelligence | None = None,
    paid_llm_opt_in: bool = False,
    llm_api_key: str | None = None,
    source_excerpts: list[str] | None = None,
) -> ContentOptimizationResult:
    """Run grounded optimization stages. Paid LLM/DO default OFF.

    Pure-ish orchestration: coverage/gaps/brief/change-plan are deterministic
    given the same inputs. Writer is isolated behind an interface.
    """
    cfg = dict(config or {})
    page = page_intelligence or extract_page_intelligence(
        html, url=url, title_hint=title_hint
    )
    gaps = build_content_gap_report(page, queryset, site_profile=site_profile)
    brief = build_optimization_brief(
        page,
        gaps,
        site_profile=site_profile,
        queryset=queryset,
        config=cfg,
    )
    writer = resolve_writer(
        paid_llm_opt_in=paid_llm_opt_in,
        api_key=llm_api_key,
        model=cfg.get("llm_model"),
    )
    draft = build_optimized_draft(
        page,
        brief,
        gaps,
        writer=writer,
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
