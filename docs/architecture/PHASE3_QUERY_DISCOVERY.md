# Phase 3 — Query discovery & SiteProfile architecture

**Status:** Implemented (2026-09-18)  
**Method versions:** `site-profile-v1` · `query-discovery-v1` · `query-set-v2`  
**Related:** ADR-024, ADR-025, ADR-026 · `docs/methodology/QUERY_DISCOVERY.md`

## Problem

Live Hashnode validation misclassified `nik-hil.hashnode.dev` as `project_management` because:

1. `INDUSTRY_KEYWORDS` treated bare `roadmap` (chrome/series UI) as PM evidence.
2. Tags (`#python`, …) were stored in `products_services`.
3. No `site_genre` vs `industry` split — SaaS templates fired on a personal tech blog.
4. First-past-the-post `Counter` over chrome votes.

## Pipeline

```
crawl → TargetSiteIdentity (unchanged)
     → SiteProfileBuilder (evidence-first)
     → generate 30–50 CandidateQuery
     → normalize + near-dup dedupe
     → quality gate (diagnostic accept|reject)
     → select ~20 (stratified, seeded) → QuerySet ready
     → paid DO web_search ONLY with explicit opt-in
```

**Frozen (no Phase 3 edits):** `security.ssrf`, `target_site` / `domain-match-v1`, `scoring.health` / `health-v1`, LLM-mention observation semantics.

## Module map

| Module | Role |
| --- | --- |
| `understanding/profile.py` | `SiteProfileField`, `StructuredSiteProfile` |
| `understanding/builder.py` | Evidence-first builder; genre gate; industry omit-by-default |
| `understanding/site.py` | Legacy `SiteUnderstanding` projection + DB persist |
| `understanding/llm_assist.py` | Opt-in stub; cannot overwrite conf≥0.70 without justification |
| `queries/generate.py` | 30–50 candidates; genre-gated templates |
| `queries/normalize.py` | NFKC + Jaccard≥0.85 near-dup |
| `queries/gate.py` | Diagnostic dimensions + `WEAK_INDUSTRY_LEAK` |
| `queries/select.py` | Stratified `query-set-v2` selection |
| `queries/store.py` | Summaries / JSON helpers |
| `queries/discovery.py` | Orchestration + legacy `DiscoveryResult` |

## Cost control

Discovery **never** auto-runs DigitalOcean `web_search`.  
`QuerySet.paid_retrieval_ready` is true only when `paid_retrieval_opt_in=true` **and** the set status is `ready`. Default opt-in is false (`AEO_PAID_RETRIEVAL_OPT_IN` / `options.paid_retrieval_opt_in`).

## Explainability trace

`site evidence → topic/entity (SiteProfileField.evidence) → CandidateQuery.source_evidence → GateDecision.reasons → QuerySet.members + profile_snapshot + target_site_audit`
