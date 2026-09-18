# Phase 3 final report — Query discovery & SiteProfile

**Date:** 2026-09-18  
**Branch:** `cursor/phase3-query-discovery-ff83`  
**Base:** `main` @ `c67124e`  
**Tests:** 107 passed, 1 skipped (was 93 passed)

## Design summary

Evidence-first `StructuredSiteProfile` with per-field confidence/provenance, `site_genre` vs `industry` split, and a `query-discovery-v1` pipeline (generate 30–50 → gate → select ~20). Paid DO retrieval is opt-in only after a ready `QuerySet`.

Frozen unchanged: SSRF, TargetSiteIdentity/`domain-match-v1`, health-v1, LLM-mention observation semantics.

## Files added/changed

### New
- `src/aeo_mvp/understanding/profile.py` — schema
- `src/aeo_mvp/understanding/builder.py` — evidence-first builder
- `src/aeo_mvp/understanding/llm_assist.py` — opt-in stub
- `src/aeo_mvp/queries/generate.py`, `normalize.py`, `gate.py`, `select.py`, `store.py`
- `tests/fixtures/hashnode/*.html`
- `tests/unit/test_site_profile.py`, `test_query_discovery_v2.py`
- `scripts/hashnode_offline_phase3.py`
- `docs/architecture/PHASE3_QUERY_DISCOVERY.md`, `ADR-024|025|026-*.md`
- `docs/methodology/QUERY_DISCOVERY.md`
- `docs/verification/PHASE3-HASHNODE-OFFLINE-2026-09-18.{md,json}`

### Extended
- `understanding/site.py` — builder + legacy projection
- `queries/discovery.py` — Phase 3 orchestration
- `pipeline/orchestrator.py` — seed/opt-in/target audit wiring
- `config.py` — `query_top_n` default 20; `paid_retrieval_opt_in`
- `DECISIONS.md` — D024–D026

## Schema changes

- Profile JSON gains wrapped fields + `site_genre`, `structured`, `warnings`, `evidence_hash`.
- `industry_category_guess` may be `null` (omit) or assertive only after thresholds.
- `discovered_queries` gains `query_set` (`query-set-v2`), gate rejects, intent breakdown, paid flags.
- Candidate intents: informational | problem_solving | comparison | recommendation | navigational | commercial.
- No DB table migrations (still JSON blobs on `site_profiles` / experiment config).

## Hashnode offline results

| Check | Result |
| --- | --- |
| Not `project_management` | PASS (`ai_ml` / genre `personal_tech_blog`) |
| Tags not in products | PASS |
| AI/agent queries selected | PASS |
| Candidates / accepted / selected | 40 / 40 / 20 |
| Paid discovery calls | None |

See `docs/verification/PHASE3-HASHNODE-OFFLINE-2026-09-18.md`.

## Tests covered

- Hashnode topic/entity extraction + PM rejection
- Unrelated-category rejection (roadmap/kanban-only)
- Normalization + near-dup
- Intent assignment (personal blog)
- Deterministic seed reproducibility
- Evidence/provenance on queries
- Insufficient-evidence / low-confidence paths
- Paid opt-in gating
- Full existing suite green
