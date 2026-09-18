# Phase 5 — Content Optimization (contract summary)

**Methodology:** `content-optimization-v1`  
**AUTHORITATIVE sheet:** [`PHASE5_RECONCILED_CONTRACTS.md`](./PHASE5_RECONCILED_CONTRACTS.md)  
**Binding Architect memo:** [`PHASE5_PAGE_INTELLIGENCE.md`](./PHASE5_PAGE_INTELLIGENCE.md)  
**ADR:** [`ADR-032-content-optimization.md`](./ADR-032-content-optimization.md)  
**Evaluator gates:** [`PHASE5_EVALUATOR_GATES.md`](./PHASE5_EVALUATOR_GATES.md)  
**D1–D7 checklist:** [`PHASE5_ALIGNMENT_DELTAS.md`](./PHASE5_ALIGNMENT_DELTAS.md)

Prefer the AUTHORITATIVE reconciled sheet over earlier partial deltas.

## Package (Architect lock)

```
aeo_mvp.content/
  page_intel.py   # PageIntelligence (page-intel-v1)
  gaps.py         # ContentGap + ContentGapReport (content-gap-v1)
  brief.py        # ContentOptimizationBrief + EditOp (opt-brief-v1)
  draft.py        # OptimizedContentDraft + DraftGenerator (opt-draft-v1)
```

## Version tags

| Artifact | Version |
| --- | --- |
| PageIntelligence | `page-intel-v1` |
| ContentGapReport | `content-gap-v1` |
| ContentOptimizationBrief | `opt-brief-v1` |
| OptimizedContentDraft | `opt-draft-v1` |

## Shared literals (sheet)

- **PageCoverage:** full \| partial \| thin \| absent \| mismatched \| unknown  
- **GapType:** missing_page · thin_coverage · no_answer_block · entity_mismatch · schema_gap · cite_miss · structure_gap · question_coverage_gap · evidence_gap · format_gap · freshness_gap · technical_extractability_gap · genre_mismatch · intent_mismatch · unsupported_claim · orphan_strength · false_coverage_nav  
- **BriefAction:** create_page \| expand_section \| add_faq \| add_howto \| add_schema \| clarify_entity  
- **EditAction:** retain \| rewrite \| expand \| remove \| add  
- **Severity:** high \| medium \| low  
- **ClaimSupport:** supported \| derived \| unsupported \| compatibility  
- **DraftStatus:** skipped_paid_false \| generated \| failed  

## Report keys

`page_intelligence` · `content_gaps` · `optimization_briefs` · `content_drafts`

## Job / API options

`content_optimization=true` · `content_draft=false` · `content_draft_provider=null`  
Aliases: `generate_draft`, `draft_paid`

## DraftGenerator

| Implementation | When |
| --- | --- |
| `NullDraftGenerator` (`name=null`) | Default → `status=skipped_paid_false` |
| `DeterministicSkeletonDraftGenerator` | When `content_draft=true` / drafting |
| Paid stub | Refuses live calls unless opted in |

## Hard rules

coverage ≠ visibility ≠ health · cite_miss only with observations · draft never → observed · paid=false / Null default · no publish · freezes untouched · missing provenance → compatibility  

## Formal VERIFY

`VERIFY-PHASE5-CONTENT-OPTIMIZATION-2026-09-18` is **Verifier-owned**.
