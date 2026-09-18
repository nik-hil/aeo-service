# Independent verification — LIVE Phase 4 Hashnode Gate G (2026-09-18)

**Overall:** PENDING Verifier Gate G (Engineering summary below — do not trust a priori)  
**Job:** `a24c1a42-faac-48da-80ae-c0b608650cbc`  
**Commit:** `faa06bb` (main after PR #8)  
**URL:** https://nik-hil.hashnode.dev/  
**Paid DO:** YES (explicit user opt-in)  
**demo_mode:** false

## Comparison caveat (required)

Phase 4 `query-set-v3` / `query-discovery-v2` ≠ Phase 3 query set (job `970aefc3…`, 15/20).  
**Do not** interpret rate deltas as site-quality improvement. Compare methodology parity / overlap only.

## Discovery

| Field | Value |
|---|---|
| method | query-discovery-v2 |
| query_set_version | query-set-v3 |
| quality_version | query-quality-v1 |
| candidates → accepted → selected | 39 → 33 → 20 |
| root_seed / effective_seed | 42 / 42 |
| seed alias | {'alias_used': 'selection_seed', 'aliases_accepted': ['selection_seed', 'query_selection_seed', 'experiment_seed'], 'effective_seed': 42, 'root_seed': 42, 'source': 'explicit', 'warnings': []} |
| selection_method | coverage_mmr_intent_budget_v1 |
| fingerprint | `8547b8bb784300fc6cfeff4b0830de86f8838c6b51d4f126716ccc22d6555432` |
| intent_breakdown | {'comparison': 3, 'informational': 7, 'navigational': 1, 'problem_solving': 6, 'recommendation': 3} |

## Visibility (hostname scope)

| Metric | Value |
|---|---|
| observations | 20 |
| strict target appeared | **17/20** |
| strict target cited | **17/20** |
| matched hosts appeared | {'nik-hil.hashnode.dev': 51} |
| matched hosts cited | {'nik-hil.hashnode.dev': 51} |
| sibling/apex bad credits | **0** |
| report mention rate | {'value': 0.7, 'numerator': 14, 'denominator': 20, 'provenance': 'estimate'} |
| report citation rate | {'value': 0.85, 'numerator': 17, 'denominator': 20, 'provenance': 'estimate'} |
| provider | digitalocean_web_search |
| experiment_kind | ai_search_visibility |
| retrieval_enabled | True |

## Health-v1 (unchanged formula)

{
  "aeo_health": {
    "value": 76.4,
    "provenance": "derived_metric",
    "formula_version": "health-v1"
  },
  "technical": {
    "value": 95.0,
    "provenance": "derived_metric"
  },
  "content": {
    "value": 69.6,
    "provenance": "derived_metric"
  },
  "entity": {
    "value": 52.5,
    "provenance": "derived_metric"
  },
  "structured_data": {
    "value": 90.0,
    "provenance": "derived_metric"
  },
  "answerability": {
    "value": 75.0,
    "provenance": "derived_metric"
  }
}

## Artifacts

- `/tmp/aeo_phase4_live_summary.json`
- `/tmp/aeo_phase4_live_report.json`
- `docs/verification/LIVE_PHASE4_HASHNODE_2026-09-18.json`
