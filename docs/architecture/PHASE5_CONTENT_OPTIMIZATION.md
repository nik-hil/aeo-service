# Phase 5 — Content Optimization

**Protocols:** `page-intelligence-v1` · `content-gap-v1` · `content-brief-v1` · `optimized-content-v1`  
**Status:** Implemented (offline fixtures first; paid LLM stub refuses live calls)  
**Base:** main @ Phase 4.1.1 provenance (`28a0b85`)

## Product goal

Grounded optimization — not a generic AI writer, not CMS publish:

```
crawl/understand → Phase 4 queries → measure (existing)
  → page intelligence → content gaps → optimization brief → optimized draft
```

Coverage here is **page-content overlap** (`direct|partial|mention|none`), separate from AI-search / LLM-mention visibility rates.

## Module map

| Module | Role |
| --- | --- |
| `optimization/page_intelligence.py` | 5.0 observed HTML facts |
| `optimization/coverage.py` | Query/topic coverage levels |
| `optimization/gaps.py` | 5.1 deterministic `ContentGapReport` |
| `optimization/brief.py` | 5.2 deterministic brief |
| `optimization/change_plan.py` | retain\|rewrite\|expand\|remove\|add |
| `optimization/draft.py` | 5.3 draft assembly |
| `optimization/llm.py` | Writer interface; heuristic default; paid stub |
| `optimization/pipeline.py` | Stage orchestration |
| `optimization/service.py` | API resolution (job/page / SSRF URL / html) |

Frozen: `security/ssrf`, `target_site`, `domains`, `scoring/health`, `visibility/digitalocean_*`, `query-set-v3`, `query-quality-v1`, provenance 4.1.1, AI-search vs LLM-mention split, paid default OFF. No `query-set-v4`. No `health-v1` change.

## Provenance

Page signals use existing `normalize_provenance` (Phase 4.1.1):

- explicit `observed|derived|compatibility` preserved
- SiteProfile `heuristic|derived_metric|llm_assist` → `derived`
- missing/unknown → `compatibility` only
- Generated draft text is **not** observed evidence

## API

`POST /api/v1/content-optimization`

Accepts **one** of:

- `job_id` + optional `page_id` (+ optional inline `queryset` / job-stored discovery)
- `source_url` (SSRF-validated live fetch)
- `html` + optional `url` (offline / fixtures)

Rejects free-form `{ "topic": "..." }` (`extra=forbid`).  
`paid_llm_opt_in` defaults **false**. Never auto-runs DO `web_search`.

## Design principles

- Pure functions for coverage / gaps / brief / change-plan
- Deterministic given same inputs; stable sort / tie-break
- LLM behind interface; tests always use heuristic writer
- Fixtures: Hashnode + SaaS + docs + ecommerce + personal blog + empty — no live web in tests

## Limitations

- Heuristic draft emits `[NEEDS_SOURCE]` placeholders; paid LLM writer is a refusing stub
- Does not publish to CMS / Hashnode / WordPress
- Does not modify `health-v1` or visibility experiment protocols
- Live `source_url` path requires network; CI uses `html` / job fixtures
- Formal `VERIFY-PHASE5-CONTENT-OPTIMIZATION-*` is Verifier-owned after product SHA

## Decisions

See `DECISIONS.md` D032.
