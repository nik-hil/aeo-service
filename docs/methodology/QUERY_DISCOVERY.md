# Query discovery methodology (`query-discovery-v1`)

**Version:** query-discovery-v1 / query-set-v2  
**Doc status:** Binding for Phase 3

## Goals

Produce a reproducible, evidence-grounded query set for AI visibility experiments without fabricating topics or leaking unrelated industry language.

## SiteProfile rules

| Rule | Detail |
| --- | --- |
| Field wrapping | Every assertive field is a `SiteProfileField` with confidence ≤ 0.40 for heuristics |
| Industry omit | `industry_category` omitted unless ≥3 strong votes, lead ≥2, ≥2 evidence classes |
| Weak tokens | Bare `roadmap` / `kanban` alone never assert `project_management` |
| Genre gate | `Blog`+`Person`, no Product/pricing → `personal_tech_blog` before SaaS industry |
| Evidence priority | titles/H1 → tags/series (topics) → About → JSON-LD → og:* → body; chrome capped |
| Tags | Topics only — never `products_services` |
| Brand | Never multi-tenant platform apex (`hashnode`, …) |

## Candidate generation

- Volume: 30–50 candidates.
- Each query: `query_id`, `text`, `intent`, `topic`, `entity`, `audience`, `funnel_stage`, `source_evidence`, `rationale`, `confidence`, `query_version`.
- Personal tech blog mix (approx): informational 35–40%, problem_solving 25–30%, recommendation 10–15%, comparison 8–12%, navigational 8–10%, commercial ≤5% (omit if no monetization).
- Forbidden for personal blogs: “cost of {blog}”, “alternatives to {blog}”, “best {PM} tool for teams”.
- ≥2 evidence classes required to seed.

## Dedup

1. NFKC → lower → collapse whitespace.  
2. Exact norm match or Jaccard ≥ 0.85 → keep higher confidence, then lower `query_id`.  
3. At most one per `(topic, intent)`.

## Quality gate (diagnostic)

Dimensions (pass/fail/warn) → `accept` | `reject` | `accept_with_warning`:

- relevance, specificity, answerability, entity_alignment, evidence_support, duplication  
- **WEAK_INDUSTRY_LEAK** — PM/SaaS language without assertive industry / wrong genre  

This is **not** a website ranking score and must not be marketed as one.

## Selection

- Default top_k ≈ 20 (`AEO_QUERY_TOP_N`).
- Stratified by intent/topic; deterministic `selection_seed`; `query_set_version=query-set-v2`.
- Explainability: `query_set_id`, profile snapshot, target_site audit, warnings, `frozen_at`, evidence hash.

## Metrics (descriptive only)

Intent / topic / entity breakdowns on the QuerySet; per-query mention/citation/appearance/coverage remain existing visibility metrics — **no new opaque AEO score**.

## Cost

Paid DO `web_search` only after ready QuerySet + explicit opt-in (ADR-026).
