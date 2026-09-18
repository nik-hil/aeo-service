# ADR-032 — Phase 5 content optimization package & contracts

**Status:** Accepted  
**Date:** 2026-09-18  
**Decisions:** D032–D034

## Context

After Phase 4.1.1 provenance, product needs grounded page optimization against frozen `query-set-v3` probes — without inventing a generic writer, mutating health-v1, or weakening evidence provenance.

## Decision

1. New package `aeo_mvp.content` with modules `page_intel`, `gaps`, `brief`, `draft` (single package; no second top-level optimizer).
2. Version tags: `page-intel-v1`, `content-gap-v1`, `opt-brief-v1`, `opt-draft-v1`.
3. Gaps + brief are pure deterministic functions. Draft behind `DraftGenerator` Protocol; default Null / `draft_paid=false`.
4. `page_coverage` is page-content overlap only; optional visibility enrich never renames coverage to AI visibility; `cite_miss` only with observations.
5. Draft artifacts stamp `content_provenance=generated` and never feed QSQ-EVD / crawl observed.
6. Reuse `query-set-v3` and Phase 4.1.1 `normalize_provenance` unchanged (no query-set-v4; no weaken QSQ-EVD).
7. Freezes untouched: ssrf, target_site, domains, health-v1, digitalocean_*, paid default OFF.

## Consequences

- API `POST /api/v1/content-optimization` accepts job/page, SSRF URL, or offline HTML — not topic generation.
- CMS publish is out of scope.
- Verifier owns formal VERIFY artifact after engineering SHA.
