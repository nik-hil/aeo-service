# ADR-026 — Paid retrieval opt-in after ready QuerySet

**Date:** 2026-09-18  
**Status:** Accepted

## Context

Running DigitalOcean `web_search` on all generated candidates would burn cost and couple discovery quality to retrieval noise.

## Decision

Pipeline stops at a **ready QuerySet**. Paid DO retrieval runs only when:

1. `QuerySet.status == ready`, and  
2. Explicit `paid_retrieval_opt_in` (job option or `AEO_PAID_RETRIEVAL_OPT_IN`).

Discovery itself never calls paid APIs. Phase 3 PRs must not include live paid DO experiments.

## Consequences

- `paid_retrieval_ready` is false by default.
- Visibility providers / `domain-match-v1` / `llm-mention-v1` semantics unchanged.
