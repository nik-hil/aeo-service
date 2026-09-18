# Phase 5 — Reconciled contracts (impl sheet)

**Authority:** Architect package/freezes/protocols + Content Optimizer field/enums  
**Package:** `aeo_mvp.content`  
**Modules:** `page_intel` · `gaps` · `brief` · `draft`  
**Versions:** `page-intel-v1` · `content-gap-v1` · `opt-brief-v1` · `opt-draft-v1`  
**Inputs:** crawl pages + analyzers + SiteProfile (read) + `QuerySet` (`query-set-v3`)  
**Optional:** visibility observations (never required for gaps/brief)  
**Date:** 2026-09-18

## Freezes

SSRF · domain-match-v1 / TargetSiteIdentity · health-v1 · LLM-mention vs AI-search · DO honesty/paid opt-in · query-set-v3 · provenance 4.1.1 (`normalize_provenance`).  
No CMS publish. Coverage ≠ visibility ≠ health. No opaque content AEO score.

## Package layout

```
src/aeo_mvp/content/
  __init__.py
  page_intel.py    # PageIntelligence
  gaps.py          # ContentGap, ContentGapReport
  brief.py         # ContentOptimizationBrief (+ edit_ops)
  draft.py         # DraftGenerator Protocol, NullDraftGenerator, OptimizedContentDraft
```

Wire: pipeline after discovery → report keys `page_intelligence`, `content_gaps`, `optimization_briefs`, `content_drafts`.  
Job options: `content_optimization` (default true), `content_draft=false`, `content_draft_provider=null`.

---

## Shared literals

```python
PageCoverage = Literal["full", "partial", "thin", "absent", "mismatched", "unknown"]

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

Severity = Literal["high", "medium", "low"]  # Architect
# map internal S|M|L → high|medium|low if needed

ClaimSupport = Literal["supported", "derived", "unsupported", "compatibility"]

DraftStatus = Literal["skipped_paid_false", "generated", "failed"]
```

Reuse `EvidenceRecord` + `normalize_provenance` from `aeo_mvp.queries.evidence`.

---

## 1. PageIntelligence (`page-intel-v1`)

Architect JSON shape + content rules:

```python
PAGE_INTEL_VERSION = "page-intel-v1"

@dataclass
class AnswerBlock:
    kind: Literal["faq", "howto", "definition", "list"]
    locator: str
    snippet: str
    provenance: str = "observed"  # only with real locator; else compatibility

@dataclass
class QueryAffinity:
    query_id: str
    score: float
    method: str = "token_overlap_v1"
    # NOT coverage status — affinities ≠ page_coverage

@dataclass
class PageIntelligence:
    page_intel_version: str = PAGE_INTEL_VERSION
    url: str
    page_id: str
    title: str | None = None
    primary_topic: dict  # {value, confidence, provenance, evidence[]} SiteProfileField-like
    entities: list[str] = field(default_factory=list)
    content_type: Literal["article", "docs", "landing", "faq", "about", "other"] = "other"
    answer_blocks: list[AnswerBlock] = field(default_factory=list)
    heading_outline: list[str] = field(default_factory=list)
    word_count: int = 0
    schema_types: list[str] = field(default_factory=list)
    query_affinities: list[QueryAffinity] = field(default_factory=list)
    limits: list[str] = field(default_factory=list)
    # content additive:
    # limits may include: js_heavy_heuristic, thin_copy, no_answer_first, heading_skip
    content_hash: str | None = None
    method: str = "deterministic_page_intel_v1"
```

Rules: heuristic confidence ≤ 0.40 unless strong extract; never invent `observed`; `query_affinities` must not be treated as coverage.

---

## 2. ContentGap + ContentGapReport (`content-gap-v1`)

```python
GAP_REPORT_VERSION = "content-gap-v1"

@dataclass
class ContentGap:
    gap_id: str
    query_id: str
    intent: str
    topic: str | None
    gap_type: GapType
    severity: Severity
    best_page_url: str | None = None
    evidence: list[dict] = field(default_factory=list)  # EvidenceRecord.to_dict()
    rationale: str = ""
    # content additive:
    page_id: str | None = None
    page_coverage: PageCoverage | None = None
    impact_class: Literal["readiness", "experiment_informed"] = "readiness"
    related_locators: list[str] = field(default_factory=list)

@dataclass
class QueryCoverageRow:
    query_id: str
    page_coverage: PageCoverage
    best_page_url: str | None = None
    visibility: dict | None = None
    # visibility only if observations: {appeared, cited, experiment_kind, provenance}

@dataclass
class ContentGapReport:
    gap_report_version: str = GAP_REPORT_VERSION
    query_set_id: str
    query_set_version: str = "query-set-v3"
    queryset_fingerprint: str | None = None
    gaps: list[ContentGap] = field(default_factory=list)
    coverage_summary: dict = field(default_factory=dict)
    # Architect: {"queries": N, "covered": C, "gapped": G}
    coverage_by_query: list[QueryCoverageRow] = field(default_factory=list)  # D1
    method: str = "deterministic_gap_v1"
    warnings: list[str] = field(default_factory=list)
```

Rules:

- Deterministic only.  
- `cite_miss` only when visibility observations exist.  
- Navigational-only inflation → `false_coverage_nav` and/or warning.  
- Do not fold covered/gapped into health-v1 or market as visibility quality.

---

## 3. ContentOptimizationBrief (`opt-brief-v1`)

```python
BRIEF_VERSION = "opt-brief-v1"

@dataclass
class EditOp:
    op_id: str
    action: EditAction
    target_locator: str | None = None  # required for retain|rewrite|expand|remove
    anchor_locator: str | None = None  # for add
    position: Literal["before", "after", "append_section", "prepend_main"] | None = None
    instruction: str = ""
    must_cite_locators: list[str] = field(default_factory=list)
    proposed_outline: list[str] = field(default_factory=list)

@dataclass
class ContentOptimizationBrief:
    brief_version: str = BRIEF_VERSION
    brief_id: str
    gap_ids: list[str]
    target_query_ids: list[str]
    action: BriefAction
    target_url: str | None = None
    outline: list[str] = field(default_factory=list)
    must_include_entities: list[str] = field(default_factory=list)
    must_include_answer_shape: Literal["definition", "steps", "faq"] | None = None
    provenance_notes: str = "derived from gap+page-intel; not a ranking promise"
    priority: float = 0.0
    # content additive:
    edit_ops: list[EditOp] = field(default_factory=list)
    success_criteria: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
```

Rules: one strong answer unit per important probe — no thin page-farm-per-query. Map `BriefAction` → `edit_ops` templates deterministically.

---

## 4. OptimizedContentDraft + DraftGenerator (`opt-draft-v1`)

```python
DRAFT_VERSION = "opt-draft-v1"

@dataclass
class UnsupportedClaimWarning:
    warning_id: str
    claim_text: str
    reason: str
    location: str | None = None
    suggested_fix: Literal[
        "remove_claim", "soften_language", "cite_existing_block", "mark_needs_source"
    ] = "mark_needs_source"
    support: ClaimSupport = "unsupported"

@dataclass
class OptimizedContentDraft:
    draft_version: str = DRAFT_VERSION
    brief_id: str
    status: DraftStatus
    generator: str  # "null" | "deterministic_skeleton" | "openai_compatible" | …
    paid: bool = False
    title: str | None = None
    body_markdown: str | None = None
    disclaimer: str = (
        "Draft suggestion only — not published; not a guarantee of AI citation."
    )
    unsupported_claims: list[UnsupportedClaimWarning] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

class DraftGenerator(Protocol):
    name: str
    async def generate(
        self, brief: ContentOptimizationBrief, *, context: DraftContext
    ) -> OptimizedContentDraft: ...

class NullDraftGenerator:
    name = "null"
    # → status=skipped_paid_false when content_draft=false / AEO_CONTENT_DRAFT=false
```

Rules: default Null; paid=false means no spend/network in CI; draft text never becomes `observed`; invented facts → `unsupported_claims`; no publish.

Optional: `DeterministicSkeletonDraftGenerator` (paid=false, no network) filling outline from brief — still not evidence.

---

## Pipeline order

1. `content/page_intel.py`  
2. `content/gaps.py`  
3. `content/brief.py`  
4. Report wiring  
5. `DraftGenerator` + Null stub  
6. Optional LLM adapter behind flag  

## Tests (must pass)

1. Same crawl + queryset fingerprint → identical gap ids/types  
2. Provenance: missing → compatibility; never invent observed  
3. No visibility → zero `cite_miss` from paid path  
4. `content_draft=false` → zero LLM HTTP; Null → `skipped_paid_false`  
5. Invented draft claim → ≥1 `unsupported_claims`  
6. Health / domain-match / ssrf goldens green  
7. No page-farm spam (cluster/cap briefs)

## Out of scope

Publishing · mutating health-v1 · forking query-set-v3 · auto paid draft/retrieval · citation guarantees · multi-site/auth/billing/frontend
