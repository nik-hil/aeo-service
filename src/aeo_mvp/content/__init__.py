"""Phase 5 content optimization — Architect package ``aeo_mvp.content``.

Modules: ``page_intel``, ``gaps``, ``brief``, ``draft``.

Contracts (AUTHORITATIVE):
- ``page-intel-v1``
- ``content-gap-v1``
- ``opt-brief-v1``
- ``opt-draft-v1``

Coverage ≠ AI visibility ≠ health-v1. Draft never → observed. Paid default OFF.
"""

from __future__ import annotations

from aeo_mvp.content.brief import build_optimization_brief
from aeo_mvp.content.draft import (
    DeterministicSkeletonDraftGenerator,
    DraftGenerator,
    NullDraftGenerator,
    PaidLLMDraftGenerator,
    build_optimized_draft,
    resolve_draft_generator,
)
from aeo_mvp.content.gaps import build_content_gap_report, page_coverage_status
from aeo_mvp.content.grounded_synth import synthesize_proposed_change
from aeo_mvp.content.models import (
    BRIEF_VERSION,
    CONTENT_OPTIMIZATION_METHODOLOGY,
    DRAFT_VERSION,
    GAP_VERSION,
    PAGE_INTEL_VERSION,
    BriefAction,
    ChangeAction,
    ClaimSupport,
    ContentChange,
    ContentGap,
    ContentGapReport,
    ContentOptimizationBrief,
    ContentProvenance,
    CoverageStatus,
    DraftStatus,
    EditAction,
    EditOp,
    GapKind,
    GapType,
    OptimizedContentDraft,
    PageCoverage,
    PageIntelligence,
    UnsupportedClaim,
    UnsupportedClaimWarning,
)
from aeo_mvp.content.page_intel import extract_page_intelligence
from aeo_mvp.content.pipeline import run_content_optimization
from aeo_mvp.content.question_opportunities import (
    build_question_opportunity_analysis,
)

__all__ = [
    "PAGE_INTEL_VERSION",
    "GAP_VERSION",
    "BRIEF_VERSION",
    "DRAFT_VERSION",
    "CONTENT_OPTIMIZATION_METHODOLOGY",
    "PageCoverage",
    "CoverageStatus",
    "GapKind",
    "GapType",
    "BriefAction",
    "EditAction",
    "ChangeAction",
    "ClaimSupport",
    "DraftStatus",
    "ContentProvenance",
    "PageIntelligence",
    "ContentGap",
    "ContentGapReport",
    "ContentChange",
    "EditOp",
    "ContentOptimizationBrief",
    "OptimizedContentDraft",
    "UnsupportedClaim",
    "UnsupportedClaimWarning",
    "extract_page_intelligence",
    "page_coverage_status",
    "build_content_gap_report",
    "build_optimization_brief",
    "build_optimized_draft",
    "DraftGenerator",
    "NullDraftGenerator",
    "DeterministicSkeletonDraftGenerator",
    "PaidLLMDraftGenerator",
    "resolve_draft_generator",
    "run_content_optimization",
    "build_question_opportunity_analysis",
    "synthesize_proposed_change",
]
