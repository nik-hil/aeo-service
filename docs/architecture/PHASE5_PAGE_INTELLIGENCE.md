# Phase 5 — Page Intelligence & Content Optimization

**Binding Architect memo**  
**Protocols:** `page-intel-v1` · `content-gap-v1` · `opt-brief-v1` · `opt-draft-v1`  
**Package:** `aeo_mvp.content` `{page_intel, gaps, brief, draft}`  
**ADRs:** ADR-032 · Decisions D032–D034  
**Base:** Phase 4.1.1 provenance lock; `query-set-v3` reused (no fork / no v4)

## 1. Product goal

Grounded optimization on a crawled page vs a frozen QuerySet:

```
crawl/understand → Phase 4 queries (query-set-v3) → measure (existing)
  → page intelligence → content gaps → optimization brief → optimized draft
```

Not a generic AI writer. Not CMS / git publish. Not an opaque content AEO score.

## 2. Hard rules

| Rule | Binding |
| --- | --- |
| Coverage | `page_coverage` ∈ full\|partial\|thin\|absent\|mismatched\|unknown — **≠** AI visibility **≠** health-v1 |
| Provenance | Reuse `normalize_provenance` (4.1.1). Draft `content_provenance=generated`. Never draft→observed / QSQ-EVD |
| cite_miss | Only when visibility **observations** exist (optional enrich) |
| Draft | `DraftGenerator` Protocol; default **Null** (`generate_draft=false`); skeleton when opted; `draft_paid=false` |
| Paid | No auto paid draft or DO retrieval |
| Freezes | ssrf, target_site, domains, health-v1, digitalocean_*, query-set-v3, query-quality-v1, AI-search vs LLM-mention |

## 3. Module map

| Module | Artifact |
| --- | --- |
| `page_intel.py` | `PageIntelligence` (page-intel-v1) — answer units, structure, entities, FAQ, schema, hostname scope |
| `gaps.py` | `ContentGapReport` (content-gap-v1) vs query-set-v3 — deterministic |
| `brief.py` | `ContentOptimizationBrief` (opt-brief-v1) — deterministic, cites inputs |
| `draft.py` | `OptimizedContentDraft` (opt-draft-v1) via `DraftGenerator` |

## 4. Gap taxonomy

**Kinds (Optimizer):** missing_answer · thin_passage · wrong_intent · missing_faq · missing_steps · entity_unclear · outdated_claim · unstructured · unsupported_claim  

**Types (page taxonomy / D2):** structure · qa_coverage · evidence · entity · format · freshness · technical · media · genre_mismatch · intent_mismatch · false_coverage_nav · metadata · query  

Report separates `readiness_gaps` vs `queryset_gaps`. Anti-pattern caveats required.

## 5. Brief structure

Scope+versions → Exec → Answerability → Gap catalog → Query×content matrix → Work queue / edit_ops (retain\|rewrite\|expand\|remove\|add) → Caveats → Anti-patterns.

## 6. Draft

- `unsupported_claims[]` required
- `content_provenance=generated`
- Null default; `DeterministicSkeletonDraftGenerator` when `generate_draft=true` and not paid
- Paid stub refuses live calls

## 7. API

`POST /api/v1/content-optimization` — `job_id`/`page_id` | SSRF `source_url` | offline `html`.  
Options: `generate_draft=false`, `draft_paid=false`. Forbids `{topic}` generate.

## 8. Alignment deltas D1–D7 (accepted)

1. `coverage_by_query` with `page_coverage`; coverage ≠ visibility ≠ health; no cite_miss without observations  
2. Extended `gap_type` page taxonomy  
3. Additive `edit_ops` under brief  
4. Draft `unsupported_claims[]`; never promote draft→observed; skeleton paid=false  
5. Report separates readiness vs queryset gaps; anti-pattern caveats  
6–7. Tests/gates C1–C10 in unit suite  

## 9. Stop conditions

No CMS/git publish · no health-v1 mutation · no weaken QSQ-EVD/provenance · no fork query-set-v3 · no auto paid draft/retrieval · no citation guarantees · no opaque content AEO score · freezes untouched.

## 10. Limitations

Heuristic/Null drafts are not polished copy. Formal `VERIFY-PHASE5-CONTENT-OPTIMIZATION-2026-09-18` is Verifier-owned after product SHA.
