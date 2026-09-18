# Independent verification — Phase 4 Query Intelligence

**Date:** 2026-09-18  
**PR under review:** https://github.com/nik-hil/aeo-service/pull/8  
**Verified SHA:** `10920caea5cdea29094d85a927ac4a5950245bdf` (`cursor/phase4-query-intelligence-0007`)  
**Base:** `main` @ `282a28cc5a76aea69047c23c035037cf3584c953`  
**Method:** independent read of code + full pytest; Engineering claims not trusted a priori  
**Paid DigitalOcean APIs:** not run (Gate G deferred)

## Overall: **PASS** (Gate G BLOCKED)

| Gate | Result |
| --- | --- |
| A Generic query generation (no AI/Hashnode hardcode on v2) | **PASS** |
| B Quality diagnostics decomposable; not site/health scores | **PASS** |
| C Coverage/diversity selection (intent budgets, max-per-topic, MMR) | **PASS** |
| D Reproducibility (fingerprint + seed aliases) | **PASS** |
| E Versioning/compat (v2 default, v1 selectable) | **PASS** |
| F No paid calls in discovery_only/dry_run | **PASS** |
| G Live experiment | **BLOCKED** (deferred; do not run paid) |
| H Frozen semantics | **PASS** |

**Pytest (independent):** `122 passed, 1 skipped, 0 failed` (123 collected)  
**Skipped:** `tests/unit/test_digitalocean_web_search.py::test_live_digitalocean_web_search_optional` (live paid DO; gated)

**Sibling JSON:** `docs/verification/VERIFY-PHASE4-QUERY-INTELLIGENCE-2026-09-18.json`

**Merge recommendation:** A–F and H PASS; G intentionally BLOCKED. H does not block. Safe to merge from freeze/cost-control perspective once product owners accept deferred live experiment.

---

## Commands run

```bash
git rev-parse HEAD
# 10920caea5cdea29094d85a927ac4a5950245bdf

python3 -m pip install -e ".[dev]"
python3 -m pytest tests/ -v --tb=line
# → 122 passed, 1 skipped, 2 warnings in ~2.3s

python3 -m pytest tests/unit/test_query_discovery_phase4.py -v --tb=line
# → 15 passed

python3 -m pytest tests/unit/test_query_discovery_phase4.py \
  tests/unit/test_ssrf.py tests/unit/test_target_site.py \
  tests/unit/test_scoring.py tests/unit/test_digitalocean_web_search.py -v --tb=line
# → 80 passed, 1 skipped

git diff origin/main...HEAD --stat
# 23 files, +3179 / −293

# Freeze paths vs main (empty diffs):
git diff origin/main...HEAD -- \
  src/aeo_mvp/security/ssrf.py \
  src/aeo_mvp/target_site.py \
  src/aeo_mvp/domains.py \
  src/aeo_mvp/scoring/health.py \
  src/aeo_mvp/visibility/digitalocean_web_search.py
# → empty (0 lines each)
```

Offline gate probes (no network / no DO key):

```bash
python3 <<'EOF'
# discover_queries dry-run twice → identical fingerprint
# resolve_seed aliases; generate_candidates_v2 garden/blog; evaluate_query_v2 title-wrap
# patch httpx.Client/AsyncClient while discovery_only + paid_retrieval_opt_in=True
EOF
```

**Live keys present:** `DO_MODEL_ACCESS_KEY=false`, `OPENAI_API_KEY=false`, `PERPLEXITY_API_KEY=false`, `AEO_PAID_RETRIEVAL_OPT_IN=false`.

---

## Gate A — Generic query generation — **PASS**

### Evidence

- Production v2 generator: `src/aeo_mvp/queries/generate_v2.py` (`candidate-gen-v2`). Module docstring and code: generic template families from SiteProfile fields only; **no** hostname gates; **no** AI-agent niche packs.
- `rg` over `generate_v2.py`: only mention of AI-agent/hostname is the negative docstring line 4. Zero `hashnode` / tool-calling pack strings in templates.
- Contrast: Phase 3 `src/aeo_mvp/queries/generate.py` still contains AI-agent pack phrases (v1 path only) — expected; Gate A scopes **v2 path**.
- Manual: blog understanding → 33 candidates via `generate_candidates_v2`; garden topics → joined text has no `"ai agent with tool calling"` / `"resource for ai agents"`.
- Tests:
  - `test_no_ai_agent_hardcode_in_v2_generator` PASSED
  - `test_hashnode_regression_no_hostname_special_case` PASSED (Hashnode fixtures; asserts no hostname special-case in method; no pack phrase `"how do i build an ai agent with tool calling?"` in selected set)

---

## Gate B — Quality diagnostics decomposable — **PASS**

### Evidence

- `src/aeo_mvp/queries/quality.py`: `QUALITY_VERSION = "query-quality-v1"`; set panels `QSQ_IDS` = SPEC, ANS, REL, ENT, EVD, DEDUP, DIV, LEAK, DET, COV.
- Per-candidate dimensions (independent probe): relevance, specificity, answerability, grammaticality_lint, entity_alignment, evidence_support, duplication, intent_label_consistency, WEAK_INDUSTRY_LEAK.
- Aggregate payload note: `"query-set diagnostics only — not an AEO/site grade"` (`aggregate_set_diagnostics`).
- Health remains separate: `compute_health` in orchestrator uses only technical/content/entity/structured_data/answerability — no quality/QSQ inputs (`src/aeo_mvp/pipeline/orchestrator.py` ~289–308; `src/aeo_mvp/scoring/health.py` WEIGHTS unchanged).
- Title-wrap reject (probe): status `reject`, reasons include `grammaticality_lint:fail:double-interrogative / title-wrap garbage`.
- Tests: `test_title_wrap_garbage_rejected`, `test_health_formula_unchanged` PASSED.

---

## Gate C — Coverage / diversity selection — **PASS**

### Evidence

- `src/aeo_mvp/queries/intent_budget.py`: `intent-budget-v1` with genre-conditioned hard min/max.
- `src/aeo_mvp/queries/select_v2.py`: `SELECTION_METHOD = "coverage_mmr_intent_budget_v1"`; Pass 1 intent minima → Pass 2 MMR (`DEFAULT_MMR_LAMBDA = 0.65`) → topic caps (`max_per_topic`); Pass 3 relax intent max only.
- Independent dry-run (seed=42, personal_tech_blog):  
  - `intent_budget_id=intent-budget-v1`, `mmr_lambda=0.65`, `max_per_topic=4`, `query_set_version=query-set-v3`  
  - intent_breakdown: informational 5, problem_solving 6, recommendation 4, comparison 3, navigational 2 (PS ≤ 6 hard max)  
  - topic_breakdown max = 4 (= cap)
- Tests: `test_intent_budgets_and_topic_cap`, `test_genre_fixtures_saas_ecommerce_docs`, `test_candidate_pool_target_and_persisted_rejects` PASSED.

---

## Gate D — Reproducibility — **PASS**

### Evidence

- `src/aeo_mvp/queries/seed.py`: aliases `selection_seed` | `query_selection_seed` | `experiment_seed` → `root_seed` + `effective_seed` + `alias_used` / `source`.
- Probe aliases → effective equals root for ints 42 / 7 / 99; wrong key `seed` yields `SEED_ALIAS_MISMATCH` (covered by unit test).
- Same snapshot + seed=42 + `frozen_at` twice:  
  - fingerprint `689255c05dfbea4d6507fd46ca3139980df9ba0460bfa780fded89863db0120e` identical  
  - ordered query ids/text identical  
  - `replay_discovery_fingerprint` equal  
  - `root_seed=42`, `effective_seed=42`, `alias_used=selection_seed`
- Tests: `test_seed_aliases_selection_seed_honored`, `test_dry_run_replay_identical_fingerprint`, `test_different_seed_deterministic_but_may_differ` PASSED.

---

## Gate E — Versioning / compat — **PASS**

### Evidence

- `discover_queries` default `_normalize_version(...)` → **v2** when unset (`src/aeo_mvp/queries/discovery.py`).
- Probe: default → `query-discovery-v2` / `query-set-v3` + diagnostics + `representativeness-v1`.
- Explicit `discovery_version="v1"` → `query-discovery-v1` / `query-set-v2` (Phase 3 artifact shape still produced).
- Tests: `test_historical_v1_compat`, `test_dry_run_replay_identical_fingerprint` (asserts v2 method/set version), legacy helpers in `test_query_discovery_v2.py` still green in full suite.

---

## Gate F — No paid calls in discovery_only / dry_run — **PASS**

### Evidence

- Discovery: `paid = False if dry else bool(paid_retrieval_opt_in)` (`discovery.py` ~258–260). Dry from `discovery_only` / options `discovery_only` / `dry_run`.
- Orchestrator: `if discovery_only: paid_opt_in = False` then skips visibility providers (`orchestrator.py` ~261–268, ~313–331; `provider_name="discovery_only"`, `runs_per_prompt=0`).
- Probe: `discovery_only=True` + `paid_retrieval_opt_in=True` → result `paid_retrieval_opt_in=False`, `paid_retrieval_ready=False`; `httpx.Client` / `AsyncClient` **not called**.
- Config default `paid_retrieval_opt_in=False` (`config.py`).
- Tests: `test_paid_opt_in_default_off_and_no_network` PASSED; live DO test skipped (not executed).

---

## Gate G — Live experiment — **BLOCKED**

Deferred per brief / methodology: offline + dry-run first; optional paid run only after A–F.  
**Not executed.** No `DO_MODEL_ACCESS_KEY`. Does not fail overall verification; live Hashnode/DO AI-search experiment remains future work after freeze of a QuerySet from dry-run.

---

## Gate H — Frozen semantics — **PASS**

| Freeze surface | Evidence |
| --- | --- |
| SSRF | `git diff origin/main...HEAD -- src/aeo_mvp/security/ssrf.py` empty; `tests/unit/test_ssrf.py` 13 passed |
| domain-match-v1 / TargetSiteIdentity | `target_site.py` + `domains.py` empty vs main; Hashnode matrix tests passed; probe audit `match_rule_version=domain-match-v1`, `match_scope=hostname`, `registrable_domain=hashnode.dev` |
| health-v1 | `scoring/health.py` empty vs main; `HEALTH_FORMULA_VERSION=health-v1`; WEIGHTS `{technical:0.25, content:0.25, entity:0.2, structured_data:0.15, answerability:0.15}`; `test_health_*` passed |
| LLM-mention vs AI-search | DO capabilities `experiment_kinds=['ai_search_visibility']`, `retrieval_enabled=True`, `measures_consumer_ui=False`; OpenAI-compatible / Demo = `llm_mention` only; orchestrator still branches on `retrieval_enabled` for metric names |
| DO provider honesty | `digitalocean_web_search.py` **0-line diff** vs main; source retains “Never fabricates”, requires web_search evidence, `domain-match-v1`, `ai-search-vis-v1`; offline DO unit tests passed; live test skipped only |

**H FAIL would block merge recommendation — not applicable (PASS).**

---

## Pytest inventory (independent)

| Suite | Result |
| --- | --- |
| Full `tests/` | 122 passed, 1 skipped, 0 failed (123 collected) |
| Phase 4 `test_query_discovery_phase4.py` | 15 passed |
| Freeze bundle (ssrf + target_site + scoring + DO + phase4) | 80 passed, 1 skipped |

Phase 4 test names:  
`test_seed_aliases_selection_seed_honored`, `test_dry_run_replay_identical_fingerprint`, `test_different_seed_deterministic_but_may_differ`, `test_title_wrap_garbage_rejected`, `test_no_ai_agent_hardcode_in_v2_generator`, `test_exact_and_semantic_near_dup`, `test_intent_budgets_and_topic_cap`, `test_candidate_pool_target_and_persisted_rejects`, `test_insufficient_content_grace`, `test_genre_fixtures_saas_ecommerce_docs`, `test_hashnode_regression_no_hostname_special_case`, `test_historical_v1_compat`, `test_paid_opt_in_default_off_and_no_network`, `test_health_formula_unchanged`, `test_evidence_provenance_on_v2_queries`.

---

## Diff scope note

Phase 4 touches discovery/orchestrator/schemas + new query modules + docs/ADRs. Freeze paths listed under Gate H are untouched relative to `main` @ `282a28c`.
