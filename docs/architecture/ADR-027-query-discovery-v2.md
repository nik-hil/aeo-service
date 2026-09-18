# ADR-027 — Query discovery v2 / query-set-v3

**Date:** 2026-09-18  
**Status:** Accepted  
**Extends:** ADR-025 (v1 remains selectable)

## Context

Phase 3 live Hashnode runs showed: seed alias mismatch (`selection_seed` ignored),
inert quality gate (0 rejects), AI-agent template overfit, soft intent strata,
topic monopoly, and no full candidate persistence for dry-run replay.

## Decision

Adopt versioned Phase 4 pipeline (default):

- `query-discovery-v2` / `candidate-gen-v2` — generic template families from
  SiteProfile fields; no niche/hostname hardcoding in core.
- `query-quality-v1` — decomposable diagnostics incl. grammaticality lint.
- `intent-budget-v1` — hard min/max per intent (genre-conditioned).
- `query-set-v3` — coverage-aware selection + lexical MMR (λ≈0.65) + max-per-topic.
- Seed aliases: `selection_seed` | `query_selection_seed` | `experiment_seed`;
  persist `root_seed`, `effective_seed`, `seed_resolution`.
- Persist full `candidates[]` + `rejected[]` + representativeness report.
- `discovery_only` / `dry_run` stops before paid retrieval.

Prior `query-discovery-v1` remains available via `query_discovery_version=v1`.

## Consequences

- Default discovery produces `query-set-v3` fingerprints for replay.
- Query diagnostics never enter `health-v1`.
- Paid DO remains opt-in default OFF (ADR-026).
