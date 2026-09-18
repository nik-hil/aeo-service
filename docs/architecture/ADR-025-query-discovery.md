# ADR-025 — Query discovery v1 (generate → gate → select)

**Date:** 2026-09-18  
**Status:** Accepted

## Context

P1 discovery emitted ~10 template queries driven by misclassified industry, including “cost of {blog}” and “best project management tool”.

## Decision

Adopt `query-discovery-v1`:

1. Generate 30–50 `CandidateQuery` with intents  
   `{informational, problem_solving, comparison, recommendation, navigational, commercial}`.
2. Require ≥2 non-chrome evidence classes per seeded query.
3. Genre-gated templates (personal tech blog intent mix; omit SaaS commercial/alternatives).
4. Diagnostic **quality gate** (not a ranking score) with dimensions including `WEAK_INDUSTRY_LEAK`.
5. Deterministic stratified selection → `query-set-v2` (~20 members, configurable seed).

## Consequences

- Default `AEO_QUERY_TOP_N=20`.
- Legacy `DiscoveredQuery` / `DiscoveryResult` remain for orchestrator/report.
- No new opaque single AEO score; metrics are descriptive breakdowns only.
