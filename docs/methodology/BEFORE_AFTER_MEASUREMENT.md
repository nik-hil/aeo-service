# Before/after AEO measurement (`aeo-before-after-v1`)

**Status:** Phase 6 measurement methodology  
**Code:** `aeo_mvp.measurement.before_after`  
**Scripts:** `scripts/compare_job_reports.py`, `scripts/phase6_fixture_before_after.py`

## Purpose

Record a reproducible **baseline**, map **recommendations → website changes → queries**, measure a **post-change** snapshot, and classify evidence honestly.

## Evidence classes (required)

| Class | Meaning |
| --- | --- |
| `observed_improvement` | Same AI-search methodology/parity; appearance or citation rate rose. Still not automatic causation. |
| `correlation` | Metrics moved together but parity incomplete or confounders present. |
| `hypothesis` | Fixture-simulated edits, demo/synthetic visibility, or coverage-only deltas. |
| `causal_evidence` | Reserved for controlled experiments with documented confounders ruled out. Default tooling does **not** emit this. |

## Baseline fields

- query / query_id  
- target domain  
- appeared / cited / mention estimate  
- query-set version + fingerprint + seed  
- timestamp  
- provider + experiment_kind + retrieval_enabled + paid_retrieval  

## Optimization mapping

Recommendation → Website change → Page → Queries affected → Expected effect  
(`expected_aeo_relevance` is readiness / extractability — **not** a ranking promise)

## Honesty

- `page_coverage` ≠ AI visibility ≠ `health-v1`  
- Demo provider metrics are `demo_synthetic`  
- `llm_mention` / `openai_compatible` is **not** AI-search / DO `web_search`  
- Fixture post-change without CMS publish → `hypothesis`  
- Do not compare across different query-set versions as site-quality deltas  
- Phase 6 authoritative Hashnode baseline: job `e26c5919-…` (llm-mention; `paid_do_calls=0`)  

