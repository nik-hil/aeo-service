# ADR-028 — Query quality diagnostics v1 (not site grade)

**Date:** 2026-09-18  
**Status:** Accepted

## Context

Phase 3 gate rejected 0 live candidates and accepted title-wrap garbage
(“How does Why does … work?”). Product risk: folding query “quality” into Health
or marketing an opaque AEO score.

## Decision

Ship `query-quality-v1` with **decomposable** dimensions (pass/warn/fail):

relevance, specificity, answerability, grammaticality_lint, entity_alignment,
evidence_support, duplication, intent_label_consistency, WEAK_INDUSTRY_LEAK.

Set-level panels use QSQ-* IDs (see `docs/methodology/QUERY_SET_QUALITY.md`).
Forbidden: single website-quality / AEO grade; any fold into `health-v1`.

## Consequences

- Title-wrap / double-interrogative candidates are rejected.
- Reports label diagnostics as query-set metadata only.
