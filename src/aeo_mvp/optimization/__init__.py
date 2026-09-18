"""Phase 5 — grounded content optimization (page intelligence → draft).

Contracts:
- ``page-intelligence-v1``
- ``content-gap-v1``
- ``content-brief-v1``
- ``optimized-content-v1``

Not a generic AI writer. Not CMS publish. Paid LLM / DO default OFF.
"""

from __future__ import annotations

from aeo_mvp.optimization.brief import build_optimization_brief
from aeo_mvp.optimization.coverage import assess_query_coverage, coverage_level
from aeo_mvp.optimization.draft import build_optimized_draft
from aeo_mvp.optimization.gaps import build_content_gap_report
from aeo_mvp.optimization.models import (
    BRIEF_VERSION,
    DRAFT_VERSION,
    GAP_VERSION,
    PAGE_INTELLIGENCE_VERSION,
    ContentGapReport,
    ContentOptimizationBrief,
    OptimizedContentDraft,
    PageIntelligence,
)
from aeo_mvp.optimization.page_intelligence import extract_page_intelligence
from aeo_mvp.optimization.pipeline import run_content_optimization

__all__ = [
    "PAGE_INTELLIGENCE_VERSION",
    "GAP_VERSION",
    "BRIEF_VERSION",
    "DRAFT_VERSION",
    "PageIntelligence",
    "ContentGapReport",
    "ContentOptimizationBrief",
    "OptimizedContentDraft",
    "extract_page_intelligence",
    "coverage_level",
    "assess_query_coverage",
    "build_content_gap_report",
    "build_optimization_brief",
    "build_optimized_draft",
    "run_content_optimization",
]
