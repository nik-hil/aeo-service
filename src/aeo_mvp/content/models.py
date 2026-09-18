"""Versioned Phase 5 content contracts (Architect + Content Optimizer reconciled)."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal

PAGE_INTEL_VERSION = "page-intel-v1"
GAP_VERSION = "content-gap-v1"
BRIEF_VERSION = "opt-brief-v1"
DRAFT_VERSION = "opt-draft-v1"

# Page↔queryset coverage (≠ AI visibility / health)
CoverageStatus = Literal[
    "full",
    "partial",
    "thin",
    "absent",
    "mismatched",
    "unknown",
]

# Optimizer gap kinds
GapKind = Literal[
    "missing_answer",
    "thin_passage",
    "wrong_intent",
    "missing_faq",
    "missing_steps",
    "entity_unclear",
    "outdated_claim",
    "unstructured",
    "unsupported_claim",
]

# Page taxonomy (Researcher + D2)
GapType = Literal[
    "structure",
    "qa_coverage",  # Researcher: on-page question coverage
    "evidence",
    "entity",  # Researcher: entity/identity
    "format",
    "freshness",  # Researcher: freshness/accuracy
    "technical",  # Researcher: technical extractability
    "media",
    "genre_mismatch",
    "intent_mismatch",
    "false_coverage_nav",
    "metadata",
    "query",
]

# Researcher canonical taxonomy (page readiness) — display labels for gap_type
RESEARCHER_GAP_TAXONOMY: tuple[tuple[str, str], ...] = (
    ("structure", "structure"),
    ("qa_coverage", "on-page question coverage"),
    ("evidence", "evidence"),
    ("entity", "entity/identity"),
    ("format", "format"),
    ("freshness", "freshness/accuracy"),
    ("technical", "technical extractability"),
    ("media", "media"),
    ("genre_mismatch", "genre mismatch"),
)

RESEARCHER_TAXONOMY_TYPES: frozenset[str] = frozenset(t for t, _ in RESEARCHER_GAP_TAXONOMY)

GapSeverity = Literal["critical", "high", "medium", "low", "info"]
ChangeAction = Literal["retain", "rewrite", "expand", "remove", "add"]
ClaimSupport = Literal["supported", "derived", "unsupported", "compatibility"]

# Content-layer provenance (draft may be generated; never promoted to QSQ observed)
ContentProvenance = Literal["observed", "derived", "compatibility", "generated"]


@dataclass
class ObservedSignal:
    key: str
    value: Any
    provenance: ContentProvenance = "compatibility"
    evidence_class: str | None = None
    locator: str | None = None
    snippet: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {k: v for k, v in asdict(self).items() if v is not None}


@dataclass
class HeadingNode:
    level: int
    text: str
    provenance: ContentProvenance = "observed"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class AnswerUnit:
    """Extractable answer unit on the page (structure / Q→passage)."""

    unit_id: str
    kind: str  # definition | howto | faq | comparison | section
    heading: str | None = None
    passage_preview: str | None = None
    provenance: ContentProvenance = "observed"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class PageIntelligence:
    """page-intel-v1 — observed page facts + extractable answer units."""

    schema_version: str = PAGE_INTEL_VERSION
    url: str = ""
    hostname: str | None = None
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
    answer_units: list[AnswerUnit] = field(default_factory=list)
    internal_links: list[dict[str, str]] = field(default_factory=list)
    signals: list[ObservedSignal] = field(default_factory=list)
    word_count: int = 0
    target_match_scope: str = "hostname"
    method: str = "deterministic_html_v1+page-intel-v1"
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "url": self.url,
            "hostname": self.hostname,
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
            "answer_units": [u.to_dict() for u in self.answer_units],
            "internal_links": list(self.internal_links),
            "signals": [s.to_dict() for s in self.signals],
            "word_count": self.word_count,
            "target_match_scope": self.target_match_scope,
            "method": self.method,
            "warnings": list(self.warnings),
        }


@dataclass
class QueryCoverageRow:
    query_id: str
    query_text: str
    intent: str | None
    topic: str | None
    page_coverage: CoverageStatus
    matched_signals: list[str] = field(default_factory=list)
    note: str = ""
    # Visibility enrich is optional and separate — never rename to AI visibility
    visibility_enrichment: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        if d.get("visibility_enrichment") is None:
            d.pop("visibility_enrichment", None)
        return d


@dataclass
class ContentGap:
    id: str
    kind: GapKind
    gap_type: GapType
    severity: GapSeverity
    query_ids: list[str] = field(default_factory=list)
    explanation: str = ""
    evidence: list[dict[str, Any]] = field(default_factory=list)
    action: str = ""
    confidence: float = 0.0
    provenance: ContentProvenance = "derived"
    page_coverage: CoverageStatus | None = None
    taxonomy_label: str | None = None  # Researcher display label when applicable

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ContentGapReport:
    """content-gap-v1 vs query-set-v3 — diagnostics ≠ health / visibility."""

    schema_version: str = GAP_VERSION
    page_url: str = ""
    query_set_version: str = "query-set-v3"
    gaps: list[ContentGap] = field(default_factory=list)
    coverage_by_query: list[QueryCoverageRow] = field(default_factory=list)
    coverage_summary: dict[str, int] = field(default_factory=dict)
    readiness_gaps: list[str] = field(default_factory=list)
    queryset_gaps: list[str] = field(default_factory=list)
    # Researcher taxonomy catalog: {taxonomy_label: [gap_ids]}
    gap_catalog_by_taxonomy: dict[str, list[str]] = field(default_factory=dict)
    anti_pattern_caveats: list[str] = field(default_factory=list)
    method: str = "deterministic_gap_v1"
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "page_url": self.page_url,
            "query_set_version": self.query_set_version,
            "gaps": [g.to_dict() for g in self.gaps],
            "coverage_by_query": [q.to_dict() for q in self.coverage_by_query],
            "coverage_summary": dict(self.coverage_summary),
            "readiness_gaps": list(self.readiness_gaps),
            "queryset_gaps": list(self.queryset_gaps),
            "gap_catalog_by_taxonomy": dict(self.gap_catalog_by_taxonomy),
            "anti_pattern_caveats": list(self.anti_pattern_caveats),
            "method": self.method,
            "warnings": list(self.warnings),
            "gap_count": len(self.gaps),
            # Honesty markers — never fold into visibility/health
            "coverage_is_not_ai_visibility": True,
            "coverage_is_not_health_v1": True,
        }


@dataclass
class ContentChange:
    action: ChangeAction
    target: str
    reason: str
    related_query_ids: list[str] = field(default_factory=list)
    related_gap_ids: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


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
    """opt-brief-v1 — deterministic brief (zero LLM).

    Researcher section order:
    Scope+versions → Exec → Answerability → Gap catalog → Query×content matrix
    → Work queue → Caveats → Anti-patterns
    """

    schema_version: str = BRIEF_VERSION
    page_url: str = ""
    # Explicit ordered section keys (Researcher brief structure)
    section_order: list[str] = field(
        default_factory=lambda: [
            "scope",
            "executive_summary",
            "answerability",
            "gap_catalog",
            "query_content_matrix",
            "work_queue",
            "caveats",
            "anti_patterns",
        ]
    )
    scope: dict[str, Any] = field(default_factory=dict)
    executive_summary: str = ""
    answerability: dict[str, Any] = field(default_factory=dict)
    gap_catalog: dict[str, list[str]] = field(default_factory=dict)
    gap_catalog_ids: list[str] = field(default_factory=list)
    query_content_matrix: list[dict[str, Any]] = field(default_factory=list)
    work_queue: list[ContentChange] = field(default_factory=list)
    edit_ops: list[ContentChange] = field(default_factory=list)
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
    genre_format_guidance: list[str] = field(default_factory=list)
    aeo_writing_requirements: list[str] = field(default_factory=list)
    do_principles: list[str] = field(default_factory=list)
    caveats: list[str] = field(default_factory=list)
    anti_patterns: list[str] = field(default_factory=list)
    input_citations: dict[str, Any] = field(default_factory=dict)
    method: str = "deterministic_brief_v1"
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        # Emit Researcher section order first, then supporting fields
        ordered: dict[str, Any] = {
            "schema_version": self.schema_version,
            "page_url": self.page_url,
            "section_order": list(self.section_order),
            "scope": dict(self.scope),
            "executive_summary": self.executive_summary,
            "answerability": dict(self.answerability),
            "gap_catalog": dict(self.gap_catalog),
            "gap_catalog_ids": list(self.gap_catalog_ids),
            "query_content_matrix": list(self.query_content_matrix),
            "work_queue": [w.to_dict() for w in self.work_queue],
            "caveats": list(self.caveats),
            "anti_patterns": list(self.anti_patterns),
            "edit_ops": [e.to_dict() for e in self.edit_ops],
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
            "genre_format_guidance": list(self.genre_format_guidance),
            "do_principles": list(self.do_principles),
            "aeo_writing_requirements": list(self.aeo_writing_requirements),
            "input_citations": dict(self.input_citations),
            "method": self.method,
            "warnings": list(self.warnings),
        }
        return ordered


@dataclass
class UnsupportedClaim:
    claim: str
    support: ClaimSupport
    reason: str
    provenance: ContentProvenance = "generated"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class OptimizedContentDraft:
    """opt-draft-v1 — via DraftGenerator; paid=False default; never observed."""

    schema_version: str = DRAFT_VERSION
    page_url: str = ""
    title: str | None = None
    meta_description: str | None = None
    body_markdown: str = ""
    faq: list[dict[str, str]] = field(default_factory=list)
    schema_jsonld: list[dict[str, Any]] = field(default_factory=list)
    internal_links: list[dict[str, str]] = field(default_factory=list)
    change_summary: list[str] = field(default_factory=list)
    change_plan: list[ContentChange] = field(default_factory=list)
    unsupported_claims: list[UnsupportedClaim] = field(default_factory=list)
    unsupported_claim_warnings: list[str] = field(default_factory=list)
    writer: str = "null_v1"
    llm_used: bool = False
    paid_llm: bool = False
    content_provenance: ContentProvenance = "generated"
    method: str = "opt-draft-v1+null"
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
            "unsupported_claims": [u.to_dict() for u in self.unsupported_claims],
            "unsupported_claim_warnings": list(self.unsupported_claim_warnings),
            "writer": self.writer,
            "llm_used": self.llm_used,
            "paid_llm": self.paid_llm,
            "content_provenance": self.content_provenance,
            "method": self.method,
            "warnings": list(self.warnings),
        }


@dataclass
class ContentOptimizationResult:
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
