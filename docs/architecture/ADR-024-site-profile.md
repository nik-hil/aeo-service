# ADR-024 — Structured SiteProfile with per-field confidence

**Date:** 2026-09-18  
**Status:** Accepted

## Context

P1 site understanding stored flat strings (`industry_category_guess`, tag-as-product) without confidence or provenance, enabling silent heuristic promotion (Hashnode → `project_management`).

## Decision

Introduce `SiteProfileField{value, confidence, provenance, evidence[], method, model?, provider?, prompt_version?}` wrapping every assertive profile field. Heuristic confidence ≤ 0.40. `industry_category` **defaults to omit**. LLM assist is opt-in and cannot overwrite deterministic conf≥0.70 without justification (`merge_llm_field`).

Split **`site_genre`** (e.g. `personal_tech_blog`) from **`industry_category`**. Genre is gated before any SaaS industry guess.

## Consequences

- Report retains legacy `SiteUnderstanding` projection; structured payload lives under `structured`.
- Weak tokens (`roadmap`, `kanban` alone) never assert `project_management`.
- Tags/series feed **topics only**, never `products`.
