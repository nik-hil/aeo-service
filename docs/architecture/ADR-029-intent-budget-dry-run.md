# ADR-029 — Intent budgets, coverage selection & dry-run reproducibility

**Date:** 2026-09-18  
**Status:** Accepted

## Context

Soft round-robin strata allowed problem_solving overweight and topic monopoly.
Operators could not replay discovery before paying for DigitalOcean web_search.

## Decision

1. `intent-budget-v1` — hard min/max per intent; commercial may be 0 without failure
   when no monetization evidence.
2. Selection: intent minima → coverage cells → lexical MMR → topic caps (≤3–4 @ k≈20).
3. Dry-run: same snapshot + seed + versions → identical ordered `query_id`/`text`
   (`fingerprint` sha256). Zero paid calls in discovery_only.
4. Representativeness report (`representativeness-v1`) is diagnostic metadata only.

## Consequences

- `QuerySet` carries `fingerprint`, `content_hash`, `grace_mode`, budgets, MMR λ.
- Live paid runs remain out-of-band after verifier gates (not this ADR’s merge gate).
