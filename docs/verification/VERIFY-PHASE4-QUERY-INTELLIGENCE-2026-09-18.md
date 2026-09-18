# Independent verification — Phase 4 Query Intelligence (Gates A–H)

**OVERALL: PASS** (Gate G **BLOCKED**)

| Field | Value |
| --- | --- |
| Role | AEO Verifier (independent; Engineering/PR claims not trusted) |
| Date | 2026-09-18 |
| PR | https://github.com/nik-hil/aeo-service/pull/8 |
| Product SHA under test | `10920caea5cdea29094d85a927ac4a5950245bdf` |
| Branch | `cursor/phase4-query-intelligence-0007` |
| Base | `main` @ `282a28cc5a76aea69047c23c035037cf3584c953` |
| Paid DO / Gate G | **Not run** (explicitly deferred) |
| Sibling JSON | `docs/verification/VERIFY-PHASE4-QUERY-INTELLIGENCE-2026-09-18.json` |

## Per-gate summary

| Gate | Result | One-line evidence |
| --- | --- | --- |
| A Generic gen | **PASS** | `generate_v2.py` has zero AI-agent/Hashnode hardcodes; garden topics produce no agent-pack phrases; saas/ecom/docs dry-runs succeed |
| B Quality diagnostics | **PASS** | Double-interrogative junk → `reject` with `query-quality-v1` reason codes; docs state diagnostics ≠ health |
| C Coverage selection | **PASS** | `intent-budget-v1` + `coverage_mmr_intent_budget_v1` (not confidence-fill only) |
| D Reproducibility | **PASS** | Fingerprint replay identical; seed aliases resolve; `root_seed`/`effective_seed` persisted |
| E Versioning/compat | **PASS** | Default `query-discovery-v2` / `query-set-v3` / `representativeness-v1`; `v1` still selectable |
| F No paid in dry-run | **PASS** | `paid_retrieval_opt_in` default `False`; dry-run `httpx.Client` call count `0` |
| G Live / paid experiment | **BLOCKED** | Deferred by brief; no `DO_MODEL_ACCESS_KEY` live run |
| H Frozen security/visibility | **PASS** | SSRF, `domain-match-v1`, `health-v1`, LLM vs AI-search split, DO honesty unchanged; diagnostics not in Health |

**Overall rule:** FAIL if any of A–F or H fails. All of A–F and H **PASS** → **OVERALL PASS**. G does not flip overall (reported **BLOCKED**).

---

## Pytest (independent recount)

```bash
git rev-parse HEAD   # at product checkout: 10920caea5cdea29094d85a927ac4a5950245bdf
python3 -m pip install -e ".[dev]"
python3 -m pytest tests/ -v --tb=line
```

| Metric | Independent count |
| --- | --- |
| Passed | **122** |
| Skipped | **1** |
| Failed | **0** |
| Collected | **123** |
| Runtime | ~2.1–2.5s |

**Skipped (exact):** `tests/unit/test_digitalocean_web_search.py:585` — `Live DO retrieval test requires DO_MODEL_ACCESS_KEY and AEO_LIVE_RETRIEVAL_TEST=true`

Product tree `src/` + `tests/` vs `10920ca`: **unchanged** by docs-only commits on this branch.

---

## Gate A — Generic generation — PASS

**Code**
- `src/aeo_mvp/queries/generate_v2.py` — `GENERATOR = "candidate-gen-v2"`; module states no site-/niche-hardcoded regex packs.
- Grep of `generate_v2.py` for `hashnode|ChatGPT|claude|tool.?calling|resource for|ai.?agent` hardcodes: **no matches**.
- Evidence classes drawn from `SiteUnderstanding.structured` / topics only (`_evidence_classes_from_understanding`).

**Independent dry-run**
- Garden topics (`Soil amendments…`, etc.): `generate_candidates_v2` → 33 candidates; `has_ai_agent_pack=false` (no `ai agent with tool calling` / `resource for ai agents`).
- Multi-genre discovery (`selection_seed=5`, `discovery_only`): saas n=20, ecom n=19, docs n=20; all `method=query-discovery-v2`.
- Hashnode fixtures (`tests/fixtures/hashnode`): `method=query-discovery-v2`, industry `ai_ml`, genre `personal_tech_blog`, no `project management` leak; fingerprint `34a46492e7bb2c6ce071b29c370fd9b2c450cede822e0a3d0d77398e3308180a`.
- Unit coverage: `tests/unit/test_query_discovery_phase4.py::test_no_ai_agent_hardcode_in_v2_generator`, `test_genre_fixtures_saas_ecommerce_docs`, `test_hashnode_regression_no_hostname_special_case`.

---

## Gate B — Quality diagnostics — PASS

**Code:** `src/aeo_mvp/queries/quality.py` (`QUALITY_VERSION = "query-quality-v1"`).

- `DOUBLE_INTERROGATIVE_RE` / `TEMPLATE_GLUE_RE` → fail on `answerability` + `grammaticality_lint`.
- Heading-literal / title-stuff path in `_dim_specificity` (tokens > 14).
- Reasons versioned as `dimension:status:detail` plus `quality_version`.

**Independent reject**
```
text: "How does Why does an AI agent need permissions work?"
status: reject
reasons:
  - answerability:fail:ungrammatical / nonsensical template
  - grammaticality_lint:fail:double-interrogative / title-wrap garbage
quality_version: query-quality-v1
```

**Diagnostics ≠ Health:** `quality.py` header + `aggregate_set_diagnostics` state diagnostic-only. `src/aeo_mvp/scoring/health.py` has **no** imports/refs to quality, QSQ, diagnostics, query_set, or representativeness. Orchestrator `compute_health(...)` uses only technical/content/entity/structured_data/answerability (`pipeline/orchestrator.py` ~292–308).

---

## Gate C — Coverage selection — PASS

**Code**
- `src/aeo_mvp/queries/intent_budget.py` — `INTENT_BUDGET_ID = "intent-budget-v1"`; genre-conditioned min/max.
- `src/aeo_mvp/queries/select_v2.py` — `SELECTION_METHOD = "coverage_mmr_intent_budget_v1"`; Pass 1 intent minima + coverage cells → Pass 2 lexical MMR (`DEFAULT_MMR_LAMBDA = 0.65`) under caps → Pass 3 relaxed fill; topic caps `DEFAULT_MAX_PER_TOPIC = 3`.

**Independent dry-run (blog, seed 42):** `intent_budget_id=intent-budget-v1`, `selection_method=coverage_mmr_intent_budget_v1`, selected 20.

Not confidence-ranked fill alone: confidence only used for stable sort before budget/MMR passes.

---

## Gate D — Reproducibility — PASS

**Code:** `src/aeo_mvp/queries/seed.py` — aliases `selection_seed | query_selection_seed | experiment_seed`; persists `root_seed`, `effective_seed`, `alias_used`, `source`.

**Independent replay** (`discovery_only=True`, `frozen_at=2026-09-18T00:00:00Z`, blog understanding):

| Check | Result |
| --- | --- |
| Fingerprint run1 | `03962ae0256fa7e2fbca975b699856d33be4f315ad0b84ef42f4f83145de4862` |
| Fingerprint run2 | identical |
| `query_selection_seed=42` | same fingerprint |
| `experiment_seed=42` | same fingerprint |
| `root_seed` / `effective_seed` / `selection_seed` | all `42` |
| `replay_discovery_fingerprint` helper | match |

---

## Gate E — Versioning / compat — PASS

| Check | Evidence |
| --- | --- |
| Default discovery | `_normalize_version(None) → v2`; `JobOptions.query_discovery_version` default `"v2"` |
| Default method/set | dry-run → `query-discovery-v2` / `query-set-v3` |
| Representativeness | `representativeness-v1` on result |
| v1 selectable | `discovery_version='v1'` → `query-discovery-v1` / `query-set-v2` |
| API schema | `src/aeo_mvp/api/schemas.py` `JobOptions` |

---

## Gate F — No paid in dry-run — PASS

| Check | Evidence |
| --- | --- |
| Settings default | `AEO_PAID_RETRIEVAL_OPT_IN` / `paid_retrieval_opt_in=False` (`config.py`) |
| Schema default | `JobOptions.paid_retrieval_opt_in=False` |
| Discovery dry-run | `paid_retrieval_opt_in=False`, `paid_retrieval_ready=False` |
| Network | `patch(httpx.Client)` during dry-run → **0 calls** |
| Orchestrator | `discovery_only` forces `paid_opt_in=False`; dry-run path sets `retrieval_enabled=False` (`orchestrator.py` ~261–324) |
| Live test | skipped (Gate G) — no paid DO executed |

---

## Gate G — Live paid experiment — BLOCKED

Explicitly deferred. No DigitalOcean live retrieval. Skip message documents the paid gate. Does **not** fail overall under this brief.

---

## Gate H — Frozen security / visibility (spot-check) — PASS

| Freeze | Evidence |
| --- | --- |
| SSRF | `src/aeo_mvp/security/ssrf.py`; independent: block `127.0.0.1`, `169.254.169.254`, `10.0.0.1`; allow `https://example.com/`; pytest `tests/unit/test_ssrf.py` pass |
| TargetSiteIdentity / `domain-match-v1` | `MATCH_RULE_VERSION="domain-match-v1"`; Hashnode → `supplemental_multi_tenant` / hostname scope; `tests/unit/test_target_site.py` pass |
| `health-v1` | `HEALTH_FORMULA_VERSION == "health-v1"`; weights unchanged; `test_health_formula_unchanged` |
| LLM-mention vs AI-search | `aggregate_llm_metrics` vs `aggregate_ai_search_metrics`; DO provider `experiment_kind=ai_search_visibility` |
| DO honesty | Module: never fabricates; `measures_consumer_ui=false`; hard-fail on missing key/HTTP |
| Diagnostics ↛ Health | Confirmed in Gate B; scoring package has zero quality coupling |

---

## Artifacts / paths touched by verifier

- This report: `docs/verification/VERIFY-PHASE4-QUERY-INTELLIGENCE-2026-09-18.md`
- Machine JSON: `docs/verification/VERIFY-PHASE4-QUERY-INTELLIGENCE-2026-09-18.json`
- Product paths reviewed: `src/aeo_mvp/queries/{generate_v2,quality,select_v2,intent_budget,seed,discovery}.py`, `src/aeo_mvp/scoring/health.py`, `src/aeo_mvp/pipeline/orchestrator.py`, `src/aeo_mvp/security/ssrf.py`, `src/aeo_mvp/target_site.py`, `src/aeo_mvp/visibility/digitalocean_web_search.py`, `src/aeo_mvp/api/schemas.py`, `src/aeo_mvp/config.py`
- Tests: `tests/unit/test_query_discovery_phase4.py` (+ suite-wide pytest)

## Verdict

**OVERALL PASS.** Gates A–F and H independently **PASS**. Gate G **BLOCKED** (no paid DO). Query-set diagnostics do not inflate Health.
