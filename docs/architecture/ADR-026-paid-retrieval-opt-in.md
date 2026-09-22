# ADR-026 — Paid retrieval opt-in after ready QuerySet

**Date:** 2026-09-18  
**Status:** Accepted

## Context

Running DigitalOcean `web_search` on all generated candidates would burn cost and couple discovery quality to retrieval noise.

## Decision

Pipeline stops at a **ready QuerySet**. Paid DO retrieval runs only when:

1. `QuerySet.status == ready`, and  
2. Explicit opt-in via runtime env `AEO_PAID_RETRIEVAL_OPT_IN=true` (settings `paid_retrieval_opt_in`).

`AEO_PAID_RETRIEVAL_OPT_IN` is the **master** runtime switch (fail-closed): API/job
`options.paid_retrieval_opt_in=true` cannot enable spend when the env is false.
A configured DO API key alone never authorizes paid retrieval. Discovery itself
never calls paid APIs. Required credentials (`DO_MODEL_ACCESS_KEY` /
`MODEL_ACCESS_KEY`) remain mandatory after the gate opens.

## Consequences

- `paid_retrieval_ready` is false by default.
- Visibility providers / `domain-match-v1` / `llm-mention-v1` semantics unchanged.
