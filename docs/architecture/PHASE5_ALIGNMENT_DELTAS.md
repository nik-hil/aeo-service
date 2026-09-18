# Phase 5 — Content Optimizer alignment deltas D1–D7

**Status:** Accepted into Architect memo §8 + **D034**.  
**Package lock unchanged:** `aeo_mvp.content` · `page-intel-v1` · `content-gap-v1` · `opt-brief-v1` · `opt-draft-v1`.  
**Authoritative sheet:** [`PHASE5_RECONCILED_CONTRACTS.md`](./PHASE5_RECONCILED_CONTRACTS.md)

## Checklist

| Delta | Requirement | Implementation | Tests |
| --- | --- | --- | --- |
| **D1** | `coverage_by_query` with `page_coverage`; coverage ≠ visibility ≠ health; no `cite_miss` without observations | `QueryCoverageRow.page_coverage`; report honesty markers; `assess_coverage_by_query(..., visibility_observations=)` | `test_d_coverage_levels_*`, `test_d1_cite_miss_*`, `test_honesty_*`, `test_d1_d7_alignment_deltas` |
| **D2** | Extend `gap_type` with page taxonomy (structure / format / evidence / intent_mismatch / false_coverage_nav / …) | `GapType` + Researcher catalog in `models.py` / `gaps.py` | `test_c_content_gap_*`, `test_researcher_taxonomy_*`, `test_d1_d7_alignment_deltas` |
| **D3** | Additive `edit_ops` retain\|rewrite\|expand\|remove\|add under brief; no thin page farms | `ContentChange` / `brief.edit_ops` + `work_queue` | `test_g_change_plan_edit_ops`, `test_d1_d7_alignment_deltas` |
| **D4** | Draft `unsupported_claims[]` required; never promote draft→observed; skeleton `paid=false` | `OptimizedContentDraft`; `DeterministicSkeletonDraftGenerator`; `content_provenance=generated` | `test_h_*`, `test_i_*`, `test_c5_*`, `test_optimizer_domain_contracts_*` |
| **D5** | Report separates readiness vs queryset gaps; anti-pattern caveats | `readiness_gaps` / `queryset_gaps` / `anti_pattern_caveats` | `test_c_*`, `test_researcher_taxonomy_*`, `test_d1_d7_alignment_deltas` |
| **D6–D7** | Engineering notes + C1–C10 gate tests (this file + Evaluator map) | [`PHASE5_EVALUATOR_GATES.md`](./PHASE5_EVALUATOR_GATES.md); unit suite | `test_c1_*` … `test_c10_*`, `test_d1_d7_alignment_deltas` |

## Hard rules (unchanged by deltas)

- coverage ≠ visibility ≠ health  
- `cite_miss` only with visibility observations  
- draft never → observed (`content_provenance=generated`)  
- `paid=false` / Null default when `generate_draft=false`  
- no CMS publish · freezes untouched  

## Formal VERIFY

`VERIFY-PHASE5-CONTENT-OPTIMIZATION-2026-09-18` remains **Verifier-owned**.
