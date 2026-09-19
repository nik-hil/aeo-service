"""Versioned Phase 5 content contracts — AUTHORITATIVE reconciled sheet."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal

PAGE_INTEL_VERSION = "page-intel-v1"
GAP_VERSION = "content-gap-v1"
GAP_REPORT_VERSION = GAP_VERSION
BRIEF_VERSION = "opt-brief-v1"
DRAFT_VERSION = "opt-draft-v1"
CONTENT_OPTIMIZATION_METHODOLOGY = "content-optimization-v1"

# --- Shared literals (AUTHORITATIVE) ---

PageCoverage = Literal[
    "full",
    "partial",
    "thin",
    "absent",
    "mismatched",
    "unknown",
]
# Alias — Optimizer / D1 naming
CoverageStatus = PageCoverage

GapType = Literal[
    # Architect (site / queryset join)
    "missing_page",
    "thin_coverage",
    "no_answer_block",
    "entity_mismatch",
    "schema_gap",
    "cite_miss",  # only when visibility observations exist
    # Content / Researcher extensions
    "structure_gap",
    "question_coverage_gap",
    "evidence_gap",
    "format_gap",
    "freshness_gap",
    "technical_extractability_gap",
    "genre_mismatch",
    "intent_mismatch",
    "unsupported_claim",
    "orphan_strength",
    "false_coverage_nav",
]

BriefAction = Literal[
    "create_page",
    "expand_section",
    "add_faq",
    "add_howto",
    "add_schema",
    "clarify_entity",
]

EditAction = Literal["retain", "rewrite", "expand", "remove", "add"]
# Alias — Optimizer ChangeAction
ChangeAction = EditAction

Severity = Literal["high", "medium", "low"]
# Compat for older callers that used critical/info (mapped at emit time)
GapSeverity = Severity

ClaimSupport = Literal["supported", "derived", "unsupported", "compatibility"]

DraftStatus = Literal["skipped_paid_false", "generated", "failed"]

ContentType = Literal["article", "docs", "landing", "faq", "about", "other"]
AnswerBlockKind = Literal["faq", "howto", "definition", "list"]
ImpactClass = Literal["readiness", "experiment_informed"]
EditPosition = Literal["before", "after", "append_section", "prepend_main"]
SuggestedFix = Literal[
    "remove_claim",
    "soften_language",
    "cite_existing_block",
    "mark_needs_source",
]
AnswerShape = Literal["definition", "steps", "faq"]

# Content-layer provenance (draft never → observed / QSQ-EVD)
ContentProvenance = Literal["observed", "derived", "compatibility", "generated"]

# Deprecated Optimizer GapKind → sheet GapType (kept for mapping helpers / exports)
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

GAP_KIND_TO_TYPE: dict[str, GapType] = {
    "missing_answer": "missing_page",
    "thin_passage": "thin_coverage",
    "wrong_intent": "intent_mismatch",
    "missing_faq": "no_answer_block",
    "missing_steps": "no_answer_block",
    "entity_unclear": "entity_mismatch",
    "outdated_claim": "freshness_gap",
    "unstructured": "structure_gap",
    "unsupported_claim": "unsupported_claim",
}

# Legacy Researcher short labels → sheet GapType
LEGACY_TYPE_TO_SHEET: dict[str, GapType] = {
    "structure": "structure_gap",
    "qa_coverage": "question_coverage_gap",
    "evidence": "evidence_gap",
    "entity": "entity_mismatch",
    "format": "format_gap",
    "freshness": "freshness_gap",
    "technical": "technical_extractability_gap",
    "media": "format_gap",
    "genre_mismatch": "genre_mismatch",
    "intent_mismatch": "intent_mismatch",
    "false_coverage_nav": "false_coverage_nav",
    "metadata": "schema_gap",
    "query": "thin_coverage",
    **{k: v for k, v in GAP_KIND_TO_TYPE.items()},
}

RESEARCHER_GAP_TAXONOMY: tuple[tuple[str, str], ...] = (
    ("structure_gap", "structure"),
    ("question_coverage_gap", "on-page question coverage"),
    ("evidence_gap", "evidence"),
    ("entity_mismatch", "entity/identity"),
    ("format_gap", "format"),
    ("freshness_gap", "freshness/accuracy"),
    ("technical_extractability_gap", "technical extractability"),
    ("genre_mismatch", "genre mismatch"),
)

RESEARCHER_TAXONOMY_TYPES: frozenset[str] = frozenset(t for t, _ in RESEARCHER_GAP_TAXONOMY)


def normalize_gap_type(raw: str) -> GapType:
    if raw in (
        "missing_page",
        "thin_coverage",
        "no_answer_block",
        "entity_mismatch",
        "schema_gap",
        "cite_miss",
        "structure_gap",
        "question_coverage_gap",
        "evidence_gap",
        "format_gap",
        "freshness_gap",
        "technical_extractability_gap",
        "genre_mismatch",
        "intent_mismatch",
        "unsupported_claim",
        "orphan_strength",
        "false_coverage_nav",
    ):
        return raw  # type: ignore[return-value]
    return LEGACY_TYPE_TO_SHEET.get(raw, "thin_coverage")


def normalize_severity(raw: str) -> Severity:
    if raw in ("critical", "high"):
        return "high"
    if raw == "medium":
        return "medium"
    return "low"


# --- Page intelligence ---


@dataclass
class AnswerBlock:
    kind: AnswerBlockKind
    locator: str
    snippet: str
    provenance: str = "observed"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class QueryAffinity:
    query_id: str
    score: float
    method: str = "token_overlap_v1"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# Compat shims used by existing extractors
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
    """Compat answer unit — prefer AnswerBlock on the wire."""

    unit_id: str
    kind: str
    heading: str | None = None
    passage_preview: str | None = None
    provenance: ContentProvenance = "observed"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def to_answer_block(self) -> AnswerBlock:
        kind_map = {
            "faq": "faq",
            "howto": "howto",
            "definition": "definition",
            "list": "list",
            "comparison": "list",
            "section": "list",
        }
        kind = kind_map.get(self.kind, "list")
        return AnswerBlock(
            kind=kind,  # type: ignore[arg-type]
            locator=self.unit_id or self.heading or "body",
            snippet=(self.passage_preview or self.heading or "")[:500],
            provenance=self.provenance if self.provenance != "generated" else "compatibility",
        )


@dataclass
class PageIntelligence:
    """page-intel-v1 — AUTHORITATIVE shape + additive extract fields."""

    url: str = ""
    page_id: str = ""
    page_intel_version: str = PAGE_INTEL_VERSION
    title: str | None = None
    primary_topic: dict[str, Any] = field(default_factory=dict)
    entities: list[str] = field(default_factory=list)
    content_type: ContentType = "other"
    answer_blocks: list[AnswerBlock] = field(default_factory=list)
    heading_outline: list[str] = field(default_factory=list)
    word_count: int = 0
    schema_types: list[str] = field(default_factory=list)
    query_affinities: list[QueryAffinity] = field(default_factory=list)
    limits: list[str] = field(default_factory=list)
    content_hash: str | None = None
    method: str = "deterministic_page_intel_v1"

    # Additive / extract helpers (not substitutes for sheet fields)
    schema_version: str = PAGE_INTEL_VERSION  # alias of page_intel_version
    hostname: str | None = None
    meta_description: str | None = None
    h1: str | None = None
    headings: list[HeadingNode] = field(default_factory=list)
    body_signals: dict[str, Any] = field(default_factory=dict)
    topics: list[str] = field(default_factory=list)
    faq_coverage: dict[str, Any] = field(default_factory=dict)
    structured_data: dict[str, Any] = field(default_factory=dict)
    answerability_signals: dict[str, Any] = field(default_factory=dict)
    answer_units: list[AnswerUnit] = field(default_factory=list)
    internal_links: list[dict[str, str]] = field(default_factory=list)
    signals: list[ObservedSignal] = field(default_factory=list)
    target_match_scope: str = "hostname"
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        blocks = self.answer_blocks or [u.to_answer_block() for u in self.answer_units]
        outline = self.heading_outline or [h.text for h in self.headings]
        primary = dict(self.primary_topic) if self.primary_topic else {}
        if not primary and self.topics:
            primary = {
                "value": self.topics[0],
                "confidence": 0.35,
                "provenance": "derived",
                "evidence": [],
            }
        return {
            "page_intel_version": self.page_intel_version or self.schema_version,
            "url": self.url,
            "page_id": self.page_id,
            "title": self.title,
            "primary_topic": primary,
            "entities": list(self.entities),
            "content_type": self.content_type,
            "answer_blocks": [b.to_dict() for b in blocks],
            "heading_outline": list(outline),
            "word_count": self.word_count,
            "schema_types": list(self.schema_types)
            or list((self.structured_data or {}).get("types") or []),
            "query_affinities": [q.to_dict() for q in self.query_affinities],
            "limits": list(self.limits),
            "content_hash": self.content_hash,
            "method": self.method,
            # honesty / scope additives
            "schema_version": self.page_intel_version or self.schema_version,
            "hostname": self.hostname,
            "meta_description": self.meta_description,
            "h1": self.h1,
            "headings": [h.to_dict() for h in self.headings],
            "topics": list(self.topics),
            "faq_coverage": dict(self.faq_coverage) if self.faq_coverage else {},
            "body_signals": dict(self.body_signals) if self.body_signals else {},
            "structured_data": dict(self.structured_data) if self.structured_data else {},
            "answerability_signals": (
                dict(self.answerability_signals) if self.answerability_signals else {}
            ),
            "answer_units": [u.to_dict() for u in self.answer_units],
            "internal_links": [dict(x) for x in self.internal_links],
            "signals": [s.to_dict() for s in self.signals],
            "target_match_scope": self.target_match_scope,
            "warnings": list(self.warnings),
            "coverage_is_not_page_affinity": True,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PageIntelligence:
        """Rehydrate page-intel-v1 including extract additives for gap replay."""
        if not isinstance(data, dict):
            raise TypeError("PageIntelligence.from_dict expects a dict")

        def _blocks(raw: list[Any] | None) -> list[AnswerBlock]:
            out: list[AnswerBlock] = []
            for item in raw or []:
                if isinstance(item, AnswerBlock):
                    out.append(item)
                elif isinstance(item, dict):
                    out.append(
                        AnswerBlock(
                            kind=item.get("kind") or "list",  # type: ignore[arg-type]
                            locator=str(item.get("locator") or "body"),
                            snippet=str(item.get("snippet") or ""),
                            provenance=str(item.get("provenance") or "observed"),
                        )
                    )
            return out

        def _affinities(raw: list[Any] | None) -> list[QueryAffinity]:
            out: list[QueryAffinity] = []
            for item in raw or []:
                if isinstance(item, QueryAffinity):
                    out.append(item)
                elif isinstance(item, dict):
                    out.append(
                        QueryAffinity(
                            query_id=str(item.get("query_id") or ""),
                            score=float(item.get("score") or 0.0),
                            method=str(item.get("method") or "token_overlap_v1"),
                        )
                    )
            return out

        def _headings(raw: list[Any] | None) -> list[HeadingNode]:
            out: list[HeadingNode] = []
            for item in raw or []:
                if isinstance(item, HeadingNode):
                    out.append(item)
                elif isinstance(item, dict):
                    out.append(
                        HeadingNode(
                            level=int(item.get("level") or 2),
                            text=str(item.get("text") or ""),
                            provenance=str(item.get("provenance") or "observed"),  # type: ignore[arg-type]
                        )
                    )
                elif isinstance(item, str):
                    out.append(HeadingNode(level=2, text=item))
            return out

        def _units(raw: list[Any] | None) -> list[AnswerUnit]:
            out: list[AnswerUnit] = []
            for item in raw or []:
                if isinstance(item, AnswerUnit):
                    out.append(item)
                elif isinstance(item, dict):
                    out.append(
                        AnswerUnit(
                            unit_id=str(item.get("unit_id") or ""),
                            kind=str(item.get("kind") or "section"),
                            heading=item.get("heading"),
                            passage_preview=item.get("passage_preview"),
                            provenance=str(item.get("provenance") or "observed"),  # type: ignore[arg-type]
                        )
                    )
            return out

        def _signals(raw: list[Any] | None) -> list[ObservedSignal]:
            out: list[ObservedSignal] = []
            for item in raw or []:
                if isinstance(item, ObservedSignal):
                    out.append(item)
                elif isinstance(item, dict):
                    out.append(
                        ObservedSignal(
                            key=str(item.get("key") or ""),
                            value=item.get("value"),
                            provenance=str(item.get("provenance") or "compatibility"),  # type: ignore[arg-type]
                            evidence_class=item.get("evidence_class"),
                            locator=item.get("locator"),
                            snippet=item.get("snippet"),
                        )
                    )
            return out

        version = str(
            data.get("page_intel_version") or data.get("schema_version") or PAGE_INTEL_VERSION
        )
        return cls(
            url=str(data.get("url") or ""),
            page_id=str(data.get("page_id") or ""),
            page_intel_version=version,
            title=data.get("title"),
            primary_topic=dict(data.get("primary_topic") or {}),
            entities=list(data.get("entities") or []),
            content_type=data.get("content_type") or "other",  # type: ignore[arg-type]
            answer_blocks=_blocks(data.get("answer_blocks")),
            heading_outline=list(data.get("heading_outline") or []),
            word_count=int(data.get("word_count") or 0),
            schema_types=list(data.get("schema_types") or []),
            query_affinities=_affinities(data.get("query_affinities")),
            limits=list(data.get("limits") or []),
            content_hash=data.get("content_hash"),
            method=str(data.get("method") or "deterministic_page_intel_v1"),
            schema_version=version,
            hostname=data.get("hostname"),
            meta_description=data.get("meta_description"),
            h1=data.get("h1"),
            headings=_headings(data.get("headings")),
            body_signals=dict(data.get("body_signals") or {}),
            topics=list(data.get("topics") or []),
            faq_coverage=dict(data.get("faq_coverage") or {}),
            structured_data=dict(data.get("structured_data") or {}),
            answerability_signals=dict(data.get("answerability_signals") or {}),
            answer_units=_units(data.get("answer_units")),
            internal_links=[dict(x) for x in (data.get("internal_links") or [])],
            signals=_signals(data.get("signals")),
            target_match_scope=str(data.get("target_match_scope") or "hostname"),
            warnings=list(data.get("warnings") or []),
        )


# --- Gaps ---


@dataclass
class QueryCoverageRow:
    query_id: str
    page_coverage: PageCoverage
    best_page_url: str | None = None
    visibility: dict[str, Any] | None = None
    # Additive
    query_text: str = ""
    intent: str | None = None
    topic: str | None = None
    matched_signals: list[str] = field(default_factory=list)
    note: str = ""
    visibility_enrichment: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        vis = self.visibility
        if vis is None and self.visibility_enrichment is not None:
            vis = dict(self.visibility_enrichment)
        d: dict[str, Any] = {
            "query_id": self.query_id,
            "page_coverage": self.page_coverage,
            "best_page_url": self.best_page_url,
        }
        if vis is not None:
            d["visibility"] = vis
        if self.query_text:
            d["query_text"] = self.query_text
        if self.intent is not None:
            d["intent"] = self.intent
        if self.topic is not None:
            d["topic"] = self.topic
        if self.matched_signals:
            d["matched_signals"] = list(self.matched_signals)
        if self.note:
            d["note"] = self.note
        return d


@dataclass
class ContentGap:
    gap_id: str = ""
    query_id: str = ""
    intent: str = "informational"
    topic: str | None = None
    gap_type: GapType = "thin_coverage"
    severity: Severity = "medium"
    best_page_url: str | None = None
    evidence: list[dict[str, Any]] = field(default_factory=list)
    rationale: str = ""
    page_id: str | None = None
    page_coverage: PageCoverage | None = None
    impact_class: ImpactClass = "readiness"
    related_locators: list[str] = field(default_factory=list)
    # Compat additives
    id: str = ""
    kind: str | None = None
    query_ids: list[str] = field(default_factory=list)
    explanation: str = ""
    action: str = ""
    confidence: float = 0.0
    provenance: ContentProvenance = "derived"
    taxonomy_label: str | None = None

    def __post_init__(self) -> None:
        if not self.id:
            self.id = self.gap_id
        if not self.gap_id and self.id:
            self.gap_id = self.id
        if not self.query_ids and self.query_id:
            self.query_ids = [self.query_id]
        if not self.query_id and self.query_ids:
            self.query_id = self.query_ids[0]
        if not self.rationale and self.explanation:
            self.rationale = self.explanation
        if not self.explanation and self.rationale:
            self.explanation = self.rationale
        # Prefer kind→sheet type when gap_type is default thin_coverage, when
        # legacy normalizes to thin_coverage (e.g. query), or for missing_faq
        # (canonical FAQ → no_answer_block). Other legacy short labels keep their
        # sheet-native mapping (structure→structure_gap, metadata→schema_gap, …).
        if self.kind:
            mapped = GAP_KIND_TO_TYPE.get(self.kind)
            raw_type = str(self.gap_type)
            if mapped and raw_type == "thin_coverage":
                self.gap_type = mapped
            elif mapped and raw_type in LEGACY_TYPE_TO_SHEET:
                legacy_sheet = LEGACY_TYPE_TO_SHEET[raw_type]
                if legacy_sheet == "thin_coverage" or self.kind == "missing_faq":
                    self.gap_type = mapped
                else:
                    self.gap_type = legacy_sheet
            else:
                self.gap_type = normalize_gap_type(raw_type)
        else:
            self.gap_type = normalize_gap_type(str(self.gap_type))
        self.severity = normalize_severity(str(self.severity))

    def to_dict(self) -> dict[str, Any]:
        return {
            "gap_id": self.gap_id or self.id,
            "query_id": self.query_id,
            "intent": self.intent,
            "topic": self.topic,
            "gap_type": normalize_gap_type(str(self.gap_type)),
            "severity": normalize_severity(str(self.severity)),
            "best_page_url": self.best_page_url,
            "evidence": list(self.evidence),
            "rationale": self.rationale or self.explanation,
            "page_id": self.page_id,
            "page_coverage": self.page_coverage,
            "impact_class": self.impact_class,
            "related_locators": list(self.related_locators),
        }


@dataclass
class ContentGapReport:
    """content-gap-v1 — AUTHORITATIVE + D1–D5 honesty additives."""

    gap_report_version: str = GAP_REPORT_VERSION
    query_set_id: str = ""
    query_set_version: str = "query-set-v3"
    queryset_fingerprint: str | None = None
    gaps: list[ContentGap] = field(default_factory=list)
    coverage_summary: dict[str, Any] = field(default_factory=dict)
    coverage_by_query: list[QueryCoverageRow] = field(default_factory=list)
    method: str = "deterministic_gap_v1"
    warnings: list[str] = field(default_factory=list)
    # Additives
    schema_version: str = GAP_VERSION
    page_url: str = ""
    readiness_gaps: list[str] = field(default_factory=list)
    queryset_gaps: list[str] = field(default_factory=list)
    gap_catalog_by_taxonomy: dict[str, list[str]] = field(default_factory=dict)
    anti_pattern_caveats: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        summary = dict(self.coverage_summary)
        if "queries" not in summary:
            n = len(self.coverage_by_query)
            covered = sum(
                1
                for r in self.coverage_by_query
                if r.page_coverage in ("full", "partial")
            )
            summary = {
                "queries": n,
                "covered": covered,
                "gapped": max(0, n - covered),
                **{k: v for k, v in summary.items() if k not in ("queries", "covered", "gapped")},
            }
        return {
            "gap_report_version": self.gap_report_version or self.schema_version,
            "query_set_id": self.query_set_id,
            "query_set_version": self.query_set_version,
            "queryset_fingerprint": self.queryset_fingerprint,
            "gaps": [g.to_dict() for g in self.gaps],
            "coverage_summary": summary,
            "coverage_by_query": [q.to_dict() for q in self.coverage_by_query],
            "method": self.method,
            "warnings": list(self.warnings),
            "gap_count": len(self.gaps),
            "schema_version": self.gap_report_version or self.schema_version,
            "page_url": self.page_url,
            "readiness_gaps": list(self.readiness_gaps),
            "queryset_gaps": list(self.queryset_gaps),
            "gap_catalog_by_taxonomy": dict(self.gap_catalog_by_taxonomy),
            "anti_pattern_caveats": list(self.anti_pattern_caveats),
            "coverage_is_not_ai_visibility": True,
            "coverage_is_not_health_v1": True,
        }


# --- Brief ---


@dataclass
class EditOp:
    op_id: str
    action: EditAction
    target_locator: str | None = None
    anchor_locator: str | None = None
    position: EditPosition | None = None
    instruction: str = ""
    must_cite_locators: list[str] = field(default_factory=list)
    proposed_outline: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ContentChange:
    """Compat shim over EditOp (Optimizer ChangeAction naming)."""

    action: EditAction
    target: str
    reason: str
    related_query_ids: list[str] = field(default_factory=list)
    related_gap_ids: list[str] = field(default_factory=list)

    def to_edit_op(self, *, idx: int = 0) -> EditOp:
        return EditOp(
            op_id=f"op_{idx}_{self.action}_{self.target}"[:80],
            action=self.action,
            target_locator=self.target if self.action != "add" else None,
            anchor_locator=self.target if self.action == "add" else None,
            position="append_section" if self.action == "add" else None,
            instruction=self.reason,
            must_cite_locators=[],
            proposed_outline=[],
        )

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
    """opt-brief-v1 — AUTHORITATIVE + Researcher section additives."""

    brief_id: str = ""
    gap_ids: list[str] = field(default_factory=list)
    target_query_ids: list[str] = field(default_factory=list)
    action: BriefAction = "expand_section"
    brief_version: str = BRIEF_VERSION
    target_url: str | None = None
    outline: list[str] = field(default_factory=list)
    must_include_entities: list[str] = field(default_factory=list)
    must_include_answer_shape: AnswerShape | None = None
    provenance_notes: str = "derived from gap+page-intel; not a ranking promise"
    priority: float = 0.0
    edit_ops: list[EditOp] = field(default_factory=list)
    success_criteria: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    # Researcher / Additive brief fields
    schema_version: str = BRIEF_VERSION
    page_url: str = ""
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
    proposed_title: str | None = None
    proposed_meta_description: str | None = None
    proposed_h1: str | None = None
    outline_sections: list[OutlineSection] = field(default_factory=list)
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
    # Legacy edit_ops as ContentChange (synced into EditOp when needed)
    legacy_edit_ops: list[ContentChange] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        ops = list(self.edit_ops)
        if not ops and self.legacy_edit_ops:
            ops = [c.to_edit_op(idx=i) for i, c in enumerate(self.legacy_edit_ops)]
        outline_list = list(self.outline)
        if not outline_list and self.outline_sections:
            outline_list = [o.heading for o in self.outline_sections]
        gap_ids = list(self.gap_ids) or list(self.gap_catalog_ids)
        entities = list(self.must_include_entities) or list(self.entities_to_cover)
        return {
            "brief_version": self.brief_version or self.schema_version,
            "schema_version": self.brief_version or self.schema_version,
            "brief_id": self.brief_id,
            "gap_ids": gap_ids,
            "target_query_ids": list(self.target_query_ids),
            "action": self.action,
            "target_url": self.target_url or self.page_url or None,
            "outline": outline_list,
            "must_include_entities": entities,
            "must_include_answer_shape": self.must_include_answer_shape,
            "provenance_notes": self.provenance_notes,
            "priority": self.priority,
            "edit_ops": [e.to_dict() for e in ops],
            "success_criteria": list(self.success_criteria),
            "warnings": list(self.warnings),
            # Researcher additives (honest diagnostics — not ranking promises)
            "section_order": list(self.section_order),
            "scope": dict(self.scope),
            "executive_summary": self.executive_summary,
            "answerability": dict(self.answerability),
            "gap_catalog": dict(self.gap_catalog),
            "gap_catalog_ids": gap_ids,
            "query_content_matrix": list(self.query_content_matrix),
            "work_queue": [w.to_dict() for w in self.work_queue],
            "caveats": list(self.caveats),
            "anti_patterns": list(self.anti_patterns),
            "do_principles": list(self.do_principles),
            "genre_format_guidance": list(self.genre_format_guidance),
            "aeo_writing_requirements": list(self.aeo_writing_requirements),
            "proposed_title": self.proposed_title,
            "proposed_meta_description": self.proposed_meta_description,
            "proposed_h1": self.proposed_h1,
            "method": self.method,
            "page_url": self.page_url,
            "input_citations": dict(self.input_citations),
        }


# --- Draft ---


@dataclass
class UnsupportedClaimWarning:
    warning_id: str
    claim_text: str
    reason: str
    location: str | None = None
    suggested_fix: SuggestedFix = "mark_needs_source"
    support: ClaimSupport = "unsupported"
    provenance: ContentProvenance = "generated"

    @property
    def claim(self) -> str:
        return self.claim_text

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        return d


@dataclass
class UnsupportedClaim:
    """Compat shim → UnsupportedClaimWarning."""

    claim: str
    support: ClaimSupport
    reason: str
    provenance: ContentProvenance = "generated"

    def to_warning(self, *, idx: int = 0) -> UnsupportedClaimWarning:
        return UnsupportedClaimWarning(
            warning_id=f"uc_{idx}",
            claim_text=self.claim,
            reason=self.reason,
            location=None,
            suggested_fix="mark_needs_source",
            support=self.support if self.support == "unsupported" else "unsupported",
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class OptimizedContentDraft:
    """opt-draft-v1 — AUTHORITATIVE; paid=False; never observed."""

    brief_id: str = ""
    status: DraftStatus = "skipped_paid_false"
    generator: str = "null"
    draft_version: str = DRAFT_VERSION
    paid: bool = False
    title: str | None = None
    body_markdown: str | None = None
    disclaimer: str = (
        "Draft suggestion only — not published; not a guarantee of AI citation."
    )
    unsupported_claims: list[UnsupportedClaimWarning] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    # Additives / honesty
    schema_version: str = DRAFT_VERSION
    page_url: str = ""
    meta_description: str | None = None
    faq: list[dict[str, str]] = field(default_factory=list)
    schema_jsonld: list[dict[str, Any]] = field(default_factory=list)
    internal_links: list[dict[str, str]] = field(default_factory=list)
    change_summary: list[str] = field(default_factory=list)
    change_plan: list[ContentChange] = field(default_factory=list)
    unsupported_claim_warnings: list[str] = field(default_factory=list)
    writer: str = "null"
    llm_used: bool = False
    paid_llm: bool = False
    content_provenance: ContentProvenance = "generated"
    method: str = "opt-draft-v1+null"

    def to_dict(self) -> dict[str, Any]:
        claims = list(self.unsupported_claims)
        return {
            "draft_version": self.draft_version or self.schema_version,
            "schema_version": self.draft_version or self.schema_version,
            "brief_id": self.brief_id,
            "status": self.status,
            "generator": self.generator or self.writer,
            "paid": bool(self.paid or self.paid_llm),
            "title": self.title,
            "body_markdown": self.body_markdown,
            "disclaimer": self.disclaimer,
            "unsupported_claims": [c.to_dict() for c in claims],
            "warnings": list(self.warnings),
            "content_provenance": "generated",
            "paid_llm": bool(self.paid or self.paid_llm),
            "unsupported_claim_warnings": list(self.unsupported_claim_warnings)
            or [c.reason for c in claims],
            "writer": self.generator or self.writer,
            "llm_used": self.llm_used,
            "method": self.method,
            "page_url": self.page_url,
            "change_summary": list(self.change_summary),
            "change_plan": [c.to_dict() for c in self.change_plan],
            # P1-5: surface FAQ / JSON-LD honestly (may be empty when unsupported)
            "faq": [dict(f) for f in self.faq],
            "schema_jsonld": list(self.schema_jsonld),
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
        """AUTHORITATIVE report keys (lists for gaps/briefs/drafts)."""
        return {
            "page_intelligence": self.page_intelligence.to_dict(),
            "content_gaps": [self.gap_report.to_dict()],
            "optimization_briefs": [self.brief.to_dict()],
            "content_drafts": [self.draft.to_dict()],
            # Compat singular aliases
            "gap_report": self.gap_report.to_dict(),
            "brief": self.brief.to_dict(),
            "draft": self.draft.to_dict(),
            "paid_retrieval": self.paid_retrieval,
            "paid_llm": self.paid_llm or self.draft.paid or self.draft.paid_llm,
        }
