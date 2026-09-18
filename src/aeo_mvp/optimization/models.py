"""Versioned Phase 5 contracts (page-intelligence / gap / brief / draft)."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal

PAGE_INTELLIGENCE_VERSION = "page-intelligence-v1"
GAP_VERSION = "content-gap-v1"
BRIEF_VERSION = "content-brief-v1"
DRAFT_VERSION = "optimized-content-v1"

CoverageLevel = Literal["direct", "partial", "mention", "none"]
GapCategory = Literal[
    "query",
    "topic",
    "entity",
    "qa",
    "intent",
    "section",
    "evidence",
    "answerability",
    "internal_link",
    "metadata",
    "structured_data",
]
GapSeverity = Literal["critical", "high", "medium", "low", "info"]
ChangeAction = Literal["retain", "rewrite", "expand", "remove", "add"]
EvidenceProvenanceLite = Literal["observed", "derived", "compatibility"]


@dataclass
class ObservedSignal:
    """A single observed or derived page signal with provenance."""

    key: str
    value: Any
    provenance: EvidenceProvenanceLite = "compatibility"
    evidence_class: str | None = None
    locator: str | None = None
    snippet: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {k: v for k, v in asdict(self).items() if v is not None}


@dataclass
class HeadingNode:
    level: int
    text: str
    provenance: EvidenceProvenanceLite = "observed"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class PageIntelligence:
    """Stage 5.0 — observed page facts only (plus explicitly derived signals)."""

    schema_version: str = PAGE_INTELLIGENCE_VERSION
    url: str = ""
    title: str | None = None
    meta_description: str | None = None
    h1: str | None = None
    headings: list[HeadingNode] = field(default_factory=list)
    body_signals: dict[str, Any] = field(default_factory=dict)
    topics: list[str] = field(default_factory=list)
    entities: list[str] = field(default_factory=list)
    faq_coverage: dict[str, Any] = field(default_factory=dict)
    structured_data: dict[str, Any] = field(default_factory=dict)
    answerability_signals: dict[str, Any] = field(default_factory=dict)
    internal_links: list[dict[str, str]] = field(default_factory=list)
    signals: list[ObservedSignal] = field(default_factory=list)
    word_count: int = 0
    method: str = "deterministic_html_v1+page-intelligence-v1"
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "url": self.url,
            "title": self.title,
            "meta_description": self.meta_description,
            "h1": self.h1,
            "headings": [h.to_dict() for h in self.headings],
            "body_signals": dict(self.body_signals),
            "topics": list(self.topics),
            "entities": list(self.entities),
            "faq_coverage": dict(self.faq_coverage),
            "structured_data": dict(self.structured_data),
            "answerability_signals": dict(self.answerability_signals),
            "internal_links": list(self.internal_links),
            "signals": [s.to_dict() for s in self.signals],
            "word_count": self.word_count,
            "method": self.method,
            "warnings": list(self.warnings),
        }


@dataclass
class ContentGap:
    id: str
    category: GapCategory
    severity: GapSeverity
    query_ids: list[str] = field(default_factory=list)
    explanation: str = ""
    evidence: list[dict[str, Any]] = field(default_factory=list)
    action: str = ""
    confidence: float = 0.0
    provenance: EvidenceProvenanceLite = "derived"
    coverage: CoverageLevel | None = None

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        return d


@dataclass
class QueryCoverageRow:
    query_id: str
    query_text: str
    intent: str | None
    topic: str | None
    coverage: CoverageLevel
    matched_signals: list[str] = field(default_factory=list)
    note: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ContentGapReport:
    """Stage 5.1 — deterministic content gaps (≠ AI visibility)."""

    schema_version: str = GAP_VERSION
    page_url: str = ""
    gaps: list[ContentGap] = field(default_factory=list)
    query_coverage: list[QueryCoverageRow] = field(default_factory=list)
    coverage_summary: dict[str, int] = field(default_factory=dict)
    method: str = "deterministic_gap_v1"
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "page_url": self.page_url,
            "gaps": [g.to_dict() for g in self.gaps],
            "query_coverage": [q.to_dict() for q in self.query_coverage],
            "coverage_summary": dict(self.coverage_summary),
            "method": self.method,
            "warnings": list(self.warnings),
            "gap_count": len(self.gaps),
        }


@dataclass
class OutlineSection:
    heading: str
    level: int = 2
    intent: str = "informational"
    retain_improve_add: Literal["retain", "improve", "add"] = "add"
    related_query_ids: list[str] = field(default_factory=list)
    notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ContentOptimizationBrief:
    """Stage 5.2 — deterministic optimization brief."""

    schema_version: str = BRIEF_VERSION
    page_url: str = ""
    proposed_title: str | None = None
    proposed_meta_description: str | None = None
    proposed_h1: str | None = None
    outline: list[OutlineSection] = field(default_factory=list)
    retain: list[str] = field(default_factory=list)
    improve: list[str] = field(default_factory=list)
    add: list[str] = field(default_factory=list)
    questions_to_answer: list[str] = field(default_factory=list)
    entities_to_cover: list[str] = field(default_factory=list)
    faq_suggestions: list[dict[str, str]] = field(default_factory=list)
    schema_suggestions: list[str] = field(default_factory=list)
    internal_link_suggestions: list[dict[str, str]] = field(default_factory=list)
    aeo_writing_requirements: list[str] = field(default_factory=list)
    forbidden_practices: list[str] = field(default_factory=list)
    related_gap_ids: list[str] = field(default_factory=list)
    method: str = "deterministic_brief_v1"
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "page_url": self.page_url,
            "proposed_title": self.proposed_title,
            "proposed_meta_description": self.proposed_meta_description,
            "proposed_h1": self.proposed_h1,
            "outline": [o.to_dict() for o in self.outline],
            "retain": list(self.retain),
            "improve": list(self.improve),
            "add": list(self.add),
            "questions_to_answer": list(self.questions_to_answer),
            "entities_to_cover": list(self.entities_to_cover),
            "faq_suggestions": list(self.faq_suggestions),
            "schema_suggestions": list(self.schema_suggestions),
            "internal_link_suggestions": list(self.internal_link_suggestions),
            "aeo_writing_requirements": list(self.aeo_writing_requirements),
            "forbidden_practices": list(self.forbidden_practices),
            "related_gap_ids": list(self.related_gap_ids),
            "method": self.method,
            "warnings": list(self.warnings),
        }


@dataclass
class ChangePlanItem:
    action: ChangeAction
    target: str
    reason: str
    related_query_ids: list[str] = field(default_factory=list)
    related_gap_ids: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class OptimizedContentDraft:
    """Stage 5.3 — optimized draft from source + brief (LLM optional)."""

    schema_version: str = DRAFT_VERSION
    page_url: str = ""
    title: str | None = None
    meta_description: str | None = None
    body_markdown: str = ""
    faq: list[dict[str, str]] = field(default_factory=list)
    schema_jsonld: list[dict[str, Any]] = field(default_factory=list)
    internal_links: list[dict[str, str]] = field(default_factory=list)
    change_summary: list[str] = field(default_factory=list)
    change_plan: list[ChangePlanItem] = field(default_factory=list)
    unsupported_claim_warnings: list[str] = field(default_factory=list)
    writer: str = "heuristic_v1"
    llm_used: bool = False
    paid_llm: bool = False
    method: str = "optimized-content-v1+heuristic"
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "page_url": self.page_url,
            "title": self.title,
            "meta_description": self.meta_description,
            "body_markdown": self.body_markdown,
            "faq": list(self.faq),
            "schema_jsonld": list(self.schema_jsonld),
            "internal_links": list(self.internal_links),
            "change_summary": list(self.change_summary),
            "change_plan": [c.to_dict() for c in self.change_plan],
            "unsupported_claim_warnings": list(self.unsupported_claim_warnings),
            "writer": self.writer,
            "llm_used": self.llm_used,
            "paid_llm": self.paid_llm,
            "method": self.method,
            "warnings": list(self.warnings),
        }


@dataclass
class ContentOptimizationResult:
    """Full Phase 5 pipeline output."""

    page_intelligence: PageIntelligence
    gap_report: ContentGapReport
    brief: ContentOptimizationBrief
    draft: OptimizedContentDraft
    paid_retrieval: bool = False
    paid_llm: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "page_intelligence": self.page_intelligence.to_dict(),
            "gap_report": self.gap_report.to_dict(),
            "brief": self.brief.to_dict(),
            "draft": self.draft.to_dict(),
            "paid_retrieval": self.paid_retrieval,
            "paid_llm": self.paid_llm,
        }
