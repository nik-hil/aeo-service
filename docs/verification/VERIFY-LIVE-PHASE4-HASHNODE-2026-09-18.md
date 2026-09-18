# AEO Verifier — LIVE Phase 4 Hashnode Gate G

**Report ID:** `VERIFY-LIVE-PHASE4-HASHNODE-2026-09-18`  
**Date:** 2026-09-18 (Asia/Calcutta)  
**Role:** Independent AEO Verifier (do not trust Engineering claims a priori)  
**Job:** `a24c1a42-faac-48da-80ae-c0b608650cbc`  
**Commit:** `faa06bb` (`main` after PR #8 squash)  
**URL:** https://nik-hil.hashnode.dev/  
**Paid DO:** YES (explicit user/CoS Gate G authorization) — **Verifier did not start a second paid run**  
**Product source modified:** No (docs/verification only)

## Overall: **PASS** (Gate G)

| Gate | Result |
| --- | --- |
| G Live AI-search experiment (authorized paid DO) | **PASS** |
| H Frozen semantics (spot-check on live artifact) | **PASS** |

Prior dry-run Gates A–F remain PASS on `main` (see `VERIFY-PHASE4-QUERY-INTELLIGENCE-2026-09-18`).

---

## Required comparison caveat

Phase 4 `query-discovery-v2` / `query-set-v3` is **not** comparable as site-quality delta vs Phase 3 job `970aefc3-7d5a-4465-b0a8-79cb3e885458` (15/20). Different query set / selection method. Rate deltas ≠ website improvement.

Artifact caveat string confirmed present in live summary.

---

## Evidence sources (recomputed)

| Path | Role |
| --- | --- |
| `/tmp/aeo_phase4_live_summary.json` | Job summary + visibility audits |
| `/tmp/aeo_phase4_live_report.json` | Full report payload |
| `docs/verification/LIVE_PHASE4_HASHNODE_2026-09-18.json` | Same bytes as summary (334564) |
| `docs/verification/LIVE_PHASE4_HASHNODE_2026-09-18.md` | Engineering LIVE note |

Commands: independent Python recompute over JSON (no network; no DO API).

---

## Gate G checks

### Discovery / QuerySet

| Check | Claimed | Recomputed | Verdict |
| --- | --- | --- | --- |
| method | query-discovery-v2 | query-discovery-v2 | PASS |
| query_set_version | query-set-v3 | query-set-v3 | PASS |
| quality_version | query-quality-v1 | query-quality-v1 | PASS |
| candidates → accepted → selected | 39 → 33 → 20 | 39 / 33 / 20 (list lens match) | PASS |
| rejected | 6 | 6 | PASS |
| root_seed / effective_seed | 42 / 42 | 42 / 42; `alias_used=selection_seed`; `source=explicit` | PASS |
| selection_method | coverage_mmr_intent_budget_v1 | coverage_mmr_intent_budget_v1 | PASS |
| intent_budget_id | intent-budget-v1 | intent-budget-v1 | PASS |
| intent_breakdown | info 7 / PS 6 / rec 3 / cmp 3 / nav 1 | identical Counter over `queries[]` | PASS |
| max topic share | ≤4 | max topic count 3 (`max_per_topic=4`) | PASS |
| paid_retrieval_opt_in / ready | true / true | true / true; `discovery_only=false` | PASS |
| hardcoded AI-agent pack phrases in selected | absent | absent | PASS |

### Visibility (hostname / domain-match-v1)

| Check | Claimed | Recomputed | Verdict |
| --- | --- | --- | --- |
| observations | 20 | 20 audits | PASS |
| strict target appeared | 17/20 | 17/20 from `appeared` flags | PASS |
| strict target cited | 17/20 | 17/20 from `cited` flags | PASS |
| matched hosts appeared | only nik-hil.hashnode.dev | `{'nik-hil.hashnode.dev': 51}` | PASS |
| matched hosts cited | only nik-hil.hashnode.dev | `{'nik-hil.hashnode.dev': 51}` | PASS |
| sibling/apex bad credits | 0 | 0 (no host ≠ tenant hostname) | PASS |
| audit scope | hostname | all 20 audits `scope=hostname` | PASS |
| TargetSiteIdentity | hostname / supplemental_multi_tenant | match_rule_version=`domain-match-v1`; registrable=`hashnode.dev`; site_key=`nik-hil.hashnode.dev` | PASS |

### Experiment honesty

| Check | Recomputed | Verdict |
| --- | --- | --- |
| provider | digitalocean_web_search | PASS |
| experiment_kind | ai_search_visibility | PASS |
| retrieval_enabled | true | PASS |
| protocol_version | ai-search-vis-v1 | PASS |
| measures_consumer_ui | false | PASS |
| report caveats | include API ≠ consumer UI disclaimers | PASS |

Report rates (not used as Gate G pass criteria beyond consistency): citation 17/20=0.85; mention estimate 14/20=0.70; target_domain_appearance 17/20=0.85.

### Health-v1 (must not inflate from query diagnostics)

| Check | Recomputed | Verdict |
| --- | --- | --- |
| formula_version | health-v1 | PASS |
| aeo_health | 76.4 | PASS |
| weighted recompute | 0.25·95 + 0.25·69.6 + 0.20·52.5 + 0.15·90 + 0.15·75 = **76.4** | PASS |
| score keys | only technical/content/entity/structured_data/answerability (+aeo_health) | PASS |

---

## Gate G FAIL triggers (none hit)

- Would FAIL if: hostname scope credited `hashnode.dev` apex / sibling tenants; experiment_kind mislabeled as llm_mention; retrieval_enabled false while claiming AI-search; paid run without opt-in flags; health formula drift; missing Phase-3 non-comparability caveat.

---

## Artifacts written by Verifier

- `docs/verification/VERIFY-LIVE-PHASE4-HASHNODE-2026-09-18.md` (this file)
- `docs/verification/VERIFY-LIVE-PHASE4-HASHNODE-2026-09-18.json`

## Top issues

None for Gate G. Standalone note: discovery fingerprint string in summary was not reproduced via a naive sha256 of `{id,text}` pairs (implementation may hash a richer frozen payload) — not a Gate G fail; seed + ordered selection counts verified independently.
