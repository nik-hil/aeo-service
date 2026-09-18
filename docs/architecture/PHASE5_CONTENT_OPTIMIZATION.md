# Phase 5 — Content Optimization (contract summary)

**Methodology:** `content-optimization-v1`  
**Binding Architect memo:** [`PHASE5_PAGE_INTELLIGENCE.md`](./PHASE5_PAGE_INTELLIGENCE.md)  
**Reconciled sheet:** [`PHASE5_RECONCILED_CONTRACTS.md`](./PHASE5_RECONCILED_CONTRACTS.md)  
**ADR:** [`ADR-032-content-optimization.md`](./ADR-032-content-optimization.md)  
**Evaluator gates:** [`PHASE5_EVALUATOR_GATES.md`](./PHASE5_EVALUATOR_GATES.md)

This document summarizes **Content Optimizer domain contracts** reconciled with the Architect package lock.

## Package (Architect)

```
aeo_mvp.content/
  page_intel.py   # PageIntelligence
  gaps.py         # ContentGap + ContentGapReport
  brief.py        # ContentOptimizationBrief + ContentChange / edit_ops
  draft.py        # OptimizedContentDraft + DraftGenerator
```

**Not** a second top-level package. Legacy `optimization/` removed / migrated here.

## Version tags (Architect)

| Artifact | Version |
| --- | --- |
| PageIntelligence | `page-intel-v1` |
| ContentGapReport | `content-gap-v1` |
| ContentOptimizationBrief | `opt-brief-v1` |
| OptimizedContentDraft | `opt-draft-v1` |

## Enums (Content Optimizer)

```text
CoverageStatus: full | partial | thin | absent | mismatched | unknown
GapKind:        missing_answer | thin_passage | wrong_intent | missing_faq |
                missing_steps | entity_unclear | outdated_claim | unstructured |
                unsupported_claim
ChangeAction:   retain | rewrite | expand | remove | add
ClaimSupport:   supported | derived | unsupported | compatibility
```

Also (Researcher / D2): `GapType` for page taxonomy  
(`structure`, `qa_coverage`, `evidence`, `entity`, `format`, `freshness`,
`technical`, `media`, `genre_mismatch`, …).

## Models

| Type | Notes |
| --- | --- |
| `PageIntelligence` | Observed answer units; hostname-scope; provenance via 4.1.1 |
| `ContentGap` | `kind` + `gap_type` + evidence-backed |
| `ContentGapReport` | Deterministic prioritize (severity → type → id); `coverage_by_query`; readiness vs queryset split |
| `ContentChange` | `edit_ops` / work queue actions |
| `ContentOptimizationBrief` | Deterministic; zero LLM; cites inputs |
| `OptimizedContentDraft` | `paid_llm=False`; `content_provenance=generated`; `unsupported_claims[]` |

## DraftGenerator Protocol

| Implementation | When |
| --- | --- |
| `NullDraftGenerator` | Job default: `generate_draft=false` (Architect / AUTHORITATIVE) |
| `DeterministicSkeletonDraftGenerator` | **Default writer when drafting** (`generate_draft=true`, `draft_paid=false`) — Optimizer default |
| `PaidLLMDraftGenerator` | Only if `draft_paid=true` + key; stub refuses live calls |

## Rules

| Rule | Binding |
| --- | --- |
| gaps + brief | Deterministic, zero LLM |
| draft | Behind Protocol only |
| unsupported → warnings | `unsupported_claims[]` + `unsupported_claim_warnings` |
| draft never observed | `content_provenance=generated`; never feed QSQ-EVD |
| missing provenance | `normalize_provenance` → `compatibility` (4.1.1) |
| Job / API options | `content_optimization`, `generate_draft=false`, `draft_paid=false` |
| No CMS publish | Out of scope |
| No health-v1 mutation | Diagnostics ≠ health |
| Freezes | ssrf, target_site, domains, health-v1, digitalocean_*, query-set-v3, query-quality-v1, paid OFF |

## API

`POST /api/v1/content-optimization` — `job_id`/`page_id` | SSRF `source_url` | offline `html`.  
Forbids free-form `{topic}` generation.

## Alignment deltas D1–D7

See Architect memo §8 / D034. Implemented: `coverage_by_query` + `page_coverage`; extended `gap_type`; `edit_ops`; `unsupported_claims`; readiness vs queryset; anti-pattern caveats; C1–C10 tests.

## Formal VERIFY

`VERIFY-PHASE5-CONTENT-OPTIMIZATION-2026-09-18` is **Verifier-owned** after product SHA.
