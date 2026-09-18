# PHASE5_RECONCILED_CONTRACTS

Authoritative impl sheet (Architect + Content Optimizer + D1–D7).

Alignment checklist: [`PHASE5_ALIGNMENT_DELTAS.md`](./PHASE5_ALIGNMENT_DELTAS.md)  
Contract summary: [`PHASE5_CONTENT_OPTIMIZATION.md`](./PHASE5_CONTENT_OPTIMIZATION.md)

## Package

`aeo_mvp.content` — `{page_intel, gaps, brief, draft}`

## Versions

| Artifact | Version |
| --- | --- |
| PageIntelligence | page-intel-v1 |
| ContentGapReport | content-gap-v1 |
| ContentOptimizationBrief | opt-brief-v1 |
| OptimizedContentDraft | opt-draft-v1 |

## Enums

- **CoverageStatus:** full \| partial \| thin \| absent \| mismatched \| unknown  
- **GapKind:** missing_answer \| thin_passage \| wrong_intent \| missing_faq \| missing_steps \| entity_unclear \| outdated_claim \| unstructured \| unsupported_claim  
- **GapType:** structure \| qa_coverage \| evidence \| entity \| format \| freshness \| technical \| media \| genre_mismatch \| intent_mismatch \| false_coverage_nav \| metadata \| query  
- **ChangeAction:** retain \| rewrite \| expand \| remove \| add  
- **ClaimSupport:** supported \| derived \| unsupported \| compatibility  

## Hard rules

- coverage ≠ visibility ≠ health  
- cite_miss only with observations  
- draft never → observed (`content_provenance=generated`)  
- paid=false / Null default  
- no publish  
- freezes untouched  
- missing provenance → compatibility via existing `normalize_provenance`  

## Job / API options

`content_optimization` · `generate_draft=false` · `draft_paid=false`
