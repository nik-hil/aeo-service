# Architect Review — Slice 1 (Phases 0–7 MVP landing)

**Reviewer:** AEO Architect  
**Date:** 2026-09-18 (IST)  
**Tree:** `/workspace/aeo-mvp`  
**Sources of truth:** `docs/blueprint/BLUEPRINT.md` (§4–§7, §14, §5), `DECISIONS.md` (D001–D018), `docs/methodology/METRICS.md`, `docs/methodology/AI_VISIBILITY.md`, `docs/api/openapi-sketch.yaml`

---

## 1. Verdict

**PASS WITH ISSUES**

Core architecture matches the blueprint: health-v1 excludes visibility, provider boundary is intact, pipeline order is correct, crawl caps/politeness are present, demo fixtures at `https://demo.example/` are deterministic for scores/rates, and OpenAPI paths/status codes for happy paths align. No P0 honesty or formula breaks found. One P1 report-DTO correctness bug and several P2 contract/consistency gaps remain.

**Code changes in this review:** none (default: review-only; no P0 requiring surgical fix).

**Post-review closure:** ISSUE-001 fixed by Engineering; Verifier signed off Slice 1 PASS (2026-09-18).

---

## 2. Scope

Reviewed the landed MVP claiming phases 0–7:

| Phase | Area | Evidence reviewed |
| --- | --- | --- |
| 0 | Scaffold | `pyproject.toml`, `config.py`, `db/`, `api/app.py`, `GET /health` |
| 1 | Crawl | `crawler/{discover,fetch,robots}.py`, demo fixtures |
| 2 | Analyzers | `analyzers/{technical,content,entities,structured_data,base}.py` |
| 3 | Scoring | `scoring/health.py` |
| 4 | Recommendations | `recommendations/{engine,catalog}.py` |
| 5 | Visibility | `visibility/{base,demo,openai_compatible,metrics}.py` |
| 6 | Pipeline + API + report | `pipeline/orchestrator.py`, `api/{routes,schemas}.py`, `report/builder.py` |
| 7 | Tests | `tests/unit/*`, `tests/integration/*`; `pytest -q` |

Also read: package layout vs D010 / BLUEPRINT §14; OpenAPI sketch path alignment; `docs/IMPLEMENTATION_STATUS.md` for known gaps (not treated as findings unless confirmed in code).

---

## 3. Package layout vs D010 / BLUEPRINT §14

| Expected (D010 / §14) | Actual | Match |
| --- | --- | --- |
| `src/aeo_mvp/config.py` | present | ✓ |
| `src/aeo_mvp/main.py` (app factory per §14) | CLI/`uvicorn` entry only; factory is `api/app.py` | △ layout drift |
| `api/{routes,schemas}.py` | present (+ `app.py`) | ✓ (+ extra app module) |
| `db/{models,session}.py` | present | ✓ |
| `crawler/{robots,fetch,discover}.py` | present | ✓ |
| `analyzers/{technical,content,entities,structured_data,base}.py` | present | ✓ |
| `scoring/health.py` | present | ✓ |
| `visibility/{base,demo,openai_compatible,metrics}.py` | present | ✓ |
| `recommendations/{engine,catalog}.py` | present | ✓ |
| `pipeline/orchestrator.py` | present | ✓ |
| `report/builder.py` | present | ✓ |
| `demo/loader.py` + `fixtures/` | present (`pages/`, `robots.txt`, `site_map.json`, `visibility/`) | ✓ |
| `logging_config.py` | present (not listed in §14) | △ fine utility |

**Overall:** D010 module set is complete. Minor §14 naming drift: FastAPI factory lives under `api/app.py` rather than `main.py`.

---

## 4. Provider boundary

| Requirement | Finding |
| --- | --- |
| `AIVisibilityProvider` protocol | `visibility/base.py` — `name` + `async run_query(...) -> VisibilityObservation` matches AI_VISIBILITY.md / BLUEPRINT §5 |
| `DemoProvider` | `visibility/demo.py` — `name="demo"`, fixture-keyed, `provenance=synthetic_demo`, `engine_label=demo-engine` |
| `OpenAICompatibleProvider` | `visibility/openai_compatible.py` — locked system prompt, appends `Site under evaluation: {base_url}`, retry once on 429/5xx, `provenance=api_observation` |
| Selection | `pipeline/orchestrator.py` `_select_provider` — demo / openai_compatible / auto (key → live else DemoProvider + fallback flag) |
| `api` must not call LLMs | `api/routes.py` only imports orchestrator/DB/schemas — no httpx/OpenAI |
| `scoring` must not call LLMs | `scoring/health.py` only aggregates component floats — no visibility imports |

**Pass.** Visibility I/O is confined to `visibility/*` and invoked only from the orchestrator.

---

## 5. Score / visibility separation

| Check | Result | Refs |
| --- | --- | --- |
| `health-v1` weights | T0.25 C0.25 E0.20 S0.15 A0.15 | `scoring/health.py:14-20`; D014 / METRICS.md |
| Visibility rates excluded from \(H\) | `compute_health` / `health_from_components` take only five components; no mention/citation args | `scoring/health.py:27-101`; orchestrator scores before experiment (`orchestrator.py:157-176` then `178+`) |
| Worked example locked | unit test \(H=70.0\) | `tests/unit/test_scoring.py:14-17` |
| Provenance on scores | persisted on `ScoreComponent`; report `ScoreValue.provenance` | `health.py:74-98`; `report/builder.py:57-68` |
| Experiment rates separate | `experiment_metrics` + report `experiment.*` with `estimate` / `synthetic_demo` | `orchestrator.py:238-271`; `builder.py:116-123` |
| Caveats on every report | four required strings + demo fifth | `report/builder.py:24-29,70-74`; matches AI_VISIBILITY §9 |
| No banned ranking claims in app copy | caveats + findings use “sample / estimate / not a ranking” | `rg` over `src/aeo_mvp`; e2e bans strings |

**Pass for D014 / honesty.** Visibility may boost *recommendation* priority (`compute_priority` visibility_boost) — allowed by methodology; not folded into health.

---

## 6. API contracts vs OpenAPI / D011 / D013

| Contract | Expected | Actual | Notes |
| --- | --- | --- | --- |
| Liveness | `GET /health` → `{status: ok}` | `routes.py:46-48` | ✓ |
| Create | `POST /api/v1/jobs` → **202** | `routes.py:51` | ✓ |
| Get job | `GET /api/v1/jobs/{id}` | present + score summary | ✓ |
| Report | `GET .../report` | 200 when completed; 409 if not ready | ✓ paths |
| Pages | `GET .../pages` | present | ✓ |
| Job status enum D013 | pending→crawling→analyzing→scoring→experimenting→synthesizing→completed\|failed | orchestrator `_set_status` sequence | ✓ transitions |
| Options caps | max_pages≤25, max_depth≤2, runs≤5, provider enum | `schemas.JobOptions` | ✓ |
| Invalid URL | OpenAPI **400** | FastAPI/Pydantic often **422** | P2 (see issues) |
| Report `status` field | BLUEPRINT Report DTO: `"completed"` | persisted as `"synthesizing"` | **P1** (see issues) |

Spot-check: paths and method/status codes for core happy path match `openapi-sketch.yaml`. Report body shape (methodology, caveats, scores, experiment, findings, recommendations, pages_crawled, emitted_at) matches OpenAPI `Report` required set.

---

## 7. Pipeline order vs D009

Authoritative order (D009 / BLUEPRINT §4):

`create_job → discover_and_crawl → analyze_technical → analyze_content_extractability → analyze_entities → analyze_structured_data → compute_aeo_health → prepare_experiment → run_visibility_experiment → synthesize_findings → prioritize_recommendations → emit_report`

Implementation (`orchestrator.py` `run`):

1. status `crawling` → `crawl_site`
2. status `analyzing` → technical → content → entities → structured_data
3. status `scoring` → `compute_health`
4. status `experimenting` → ExperimentConfig (prepare) + provider loops (run)
5. status `synthesizing` → findings → recommendations → `build_report`
6. status `completed`

**Pass:** health before experiment; prepare folded into experimenting (no separate D013 status — consistent with D013 enum).

---

## 8. Crawl caps / politeness vs D012

| Rule | Implementation | Ref |
| --- | --- | --- |
| Max 25 pages | `min(..., 25)` in orchestrator + `crawl_live` | `orchestrator.py:132`; `discover.py:119` |
| Max depth 2 | same pattern | `orchestrator.py:133`; `discover.py:120` |
| Same-host only | `same_host` + queue filter | `discover.py:40-42,152-153,207` |
| robots.txt | fetch + `parse_robots` / skip disallow | `discover.py:131-175`; `robots.py` |
| Timeout 5s default | `AEO_CRAWL_TIMEOUT_S` default 5.0; fetch default 5.0 | `config.py:32`; `fetch.py:29` |
| UA | `AEOBot/0.1 (+research; respectful)` | `config.py:10`; `fetch.py:57-58` |
| Options only tighten | Pydantic `le=25` / `le=2`; crawl also `min` with settings | schemas + discover |

**Gap:** env `AEO_CRAWL_TIMEOUT_S` is not hard-clamped to ≤5s the way pages/depth are (P2). API `JobOptions` does not expose timeout (good).

---

## 9. Demo mode vs D006 / D016

| Rule | Finding |
| --- | --- |
| Fixtures at `https://demo.example/` | `DEMO_BASE_URL`; `site_map.json` base_url; never live-fetched in demo path | ✓ |
| Demo crawl | `crawl_demo` loads packaged HTML + robots | `discover.py:76-106` |
| DemoProvider fixtures | `fixtures/visibility/observations.json` (15 rows: 6 mentions, 2 citations) | ✓ |
| Bit-stable scores/rates | `test_demo_two_runs_identical` locks health + components + metrics | ✓ |
| Provenance | observations `synthetic_demo`; rates `synthetic_demo` for demo provider | ✓ |
| Caveat | demo-specific caveat appended | `builder.py:71-74` |

**Nuance:** full report JSON is **not** bit-identical across runs (`emitted_at`, entity UUIDs). D006 text says “scores and reports are bit-stable”; tests correctly lock scores/metrics only (P2 wording/scope).

---

## 10. Issues list

### ISSUE-001 — Report DTO `status` stuck at `synthesizing`

| | |
| --- | --- |
| **Severity** | **P1** |
| **Area** | report / API contract |
| **Refs** | `pipeline/orchestrator.py:330-332` (`build_report` then `_set_status(..., "completed")`); `report/builder.py:96` (`"status": job.status`); verified live: `job.status=completed` but `report.status=synthesizing` |
| **Cite** | BLUEPRINT Report DTO (§ end): `"status": "completed"`; OpenAPI `Report.status` |
| **Recommendation** | Set job status to `completed` **before** `build_report`, or pass an explicit `status="completed"` into the builder so persisted `report_json` matches the completed job. Add an assertion in demo/API tests: `data["status"] == "completed"`. |
| **Closure** | **Fixed 2026-09-18** — `orchestrator` now `_set_status(..., "completed")` before `build_report`; CoS confirmed live `report.status=completed` (health=87.9); Verifier Slice 1 PASS. |

### ISSUE-002 — Invalid URL status code: 422 vs OpenAPI 400

| | |
| --- | --- |
| **Severity** | **P2** |
| **Area** | API |
| **Refs** | `api/schemas.py:23-29` (validator); FastAPI default validation; `tests/integration/test_api.py:54-56` allows 422 **or** 400; `openapi-sketch.yaml` POST `/api/v1/jobs` responses `"400"` |
| **Cite** | D011 / OpenAPI sketch; BLUEPRINT §7 Errors: `400` invalid URL |
| **Recommendation** | Either map validation errors to 400 with `ErrorResponse`, or update OpenAPI sketch + BLUEPRINT to document 422. Keep one canonical client contract. |

### ISSUE-003 — Intentional demo_mode flagged as credential fallback

| | |
| --- | --- |
| **Severity** | **P2** |
| **Area** | findings / honesty labeling |
| **Refs** | `orchestrator.py:292,324` (`used_demo_fallback or bool(job.demo_mode)`); `recommendations/engine.py:145-151` meta finding “no API key was available or demo mode was forced” |
| **Cite** | AI_VISIBILITY §8 — fallback note `VIS_FALLBACK_DEMO_NO_CREDENTIALS` is for `auto` without credentials; intentional demo has its own caveat |
| **Recommendation** | Pass `used_demo_fallback` alone into synthesize/prioritize; keep demo caveat on the report. Optionally emit a distinct finding code only when auto-fallback. |

### ISSUE-004 — D006 “bit-stable reports” vs volatile report fields

| | |
| --- | --- |
| **Severity** | **P2** |
| **Area** | demo / docs |
| **Refs** | D006; `report/builder.py:151` (`utc_now_iso` for `emitted_at`); UUID ids on findings/recs; `tests/integration/test_demo_e2e.py:75-101` compares scores/metrics only |
| **Cite** | D006: “scores and reports are bit-stable” |
| **Recommendation** | Narrow D006 (or README) to “scores + visibility rates (+ optionally methodology block) bit-stable”; or freeze `emitted_at` in demo and hash a canonicalized report subset in tests. |

### ISSUE-005 — Crawl timeout env not hard-capped at 5s

| | |
| --- | --- |
| **Severity** | **P2** |
| **Area** | crawler / config |
| **Refs** | `config.py:32` (`crawl_timeout_s` unconstrained); `orchestrator.py:134` uses settings timeout; `discover.py` clamps pages/depth but not timeout |
| **Cite** | D012: per-request timeout **5s**; overrides may only tighten |
| **Recommendation** | `timeout_s = min(requested_or_settings, 5.0)` in `crawl_live` / orchestrator (mirror pages/depth). |

### ISSUE-006 — Empty observation set yields 0.0 rates, not null

| | |
| --- | --- |
| **Severity** | **P2** |
| **Area** | visibility metrics |
| **Refs** | `visibility/metrics.py:86-88` (`(m/r) if r else 0.0`) |
| **Cite** | METRICS.md §8: rates `else null` when \(R=0\) / \(P=0\) |
| **Recommendation** | Return `None` (and persist nullable / omit) when denominator is 0; rare in happy path (always 15 runs) but formula-correct. |

### ISSUE-007 — BLUEPRINT §7 “provenance map” not a top-level report field

| | |
| --- | --- |
| **Severity** | **P2** |
| **Area** | report / docs drift |
| **Refs** | BLUEPRINT §7 line on report includes “provenance map”; OpenAPI `Report` has per-field `ScoreValue.provenance` only; `builder.py` matches OpenAPI |
| **Cite** | BLUEPRINT §7 vs `openapi-sketch.yaml` `Report` |
| **Recommendation** | Align docs: either drop “provenance map” from §7 prose or add an optional top-level `provenance` object. Implementation already labels fields — acceptable for MVP if docs updated. |

### ISSUE-008 — `main.py` vs BLUEPRINT §14 app-factory location

| | |
| --- | --- |
| **Severity** | **P3** |
| **Area** | package layout |
| **Refs** | `main.py` CLI; `api/app.py` `create_app` |
| **Cite** | BLUEPRINT §14 |
| **Recommendation** | Update §14 / README entrypoint note, or re-export `app` from `main.py`. |

### ISSUE-009 — Job status not typed as enum in Pydantic schemas

| | |
| --- | --- |
| **Severity** | **P3** |
| **Area** | API schemas |
| **Refs** | `api/schemas.py:41,50` (`status: str`) |
| **Cite** | OpenAPI `JobStatus` enum; D013 |
| **Recommendation** | `Literal[...]` matching D013 for clearer OpenAPI generation from app. |

### ISSUE-010 — Soft boundary: pipeline holds SQLAlchemy `Session`

| | |
| --- | --- |
| **Severity** | **P3** |
| **Area** | component boundaries |
| **Refs** | `pipeline/orchestrator.py` throughout |
| **Cite** | BLUEPRINT §5: pipeline must not “Know … SQL dialects” |
| **Recommendation** | Acceptable for MVP; later introduce a thin repository if boundaries harden. No action required for Slice 1 acceptance. |

### ISSUE-011 — Unused `Request` import in routes

| | |
| --- | --- |
| **Severity** | **P3** |
| **Area** | polish |
| **Refs** | `api/routes.py:10` |
| **Cite** | n/a |
| **Recommendation** | Remove unused import. |

---

## 11. What’s solid

- **Honesty stack:** caveats, estimate/synthetic provenance, banned ranking language absent from product strings; findings explicitly say “sample, not a ranking.”
- **health-v1 purity:** weights and worked example match METRICS.md; visibility cannot leak into \(H\) from the scoring API surface.
- **Provider pluggability:** Protocol + Demo + OpenAI-compatible with correct auto/demo/key selection; API/scoring do not call models.
- **Pipeline discipline:** D009 order and D013 status transitions are explicit and readable.
- **Crawl politeness:** robots, same-host, UA, page/depth caps enforced in code paths used by the API.
- **Demo story:** packaged `demo.example` fixtures; 15 observations; e2e locks mention 0.4 / citation 2/15 / coverage 0.6; recommendations require evidence IDs.
- **Test signal:** `22 passed` in ~0.6s — unit formulas + robots + demo e2e + API TestClient.

---

## 12. Follow-ups for Verifier / next slice

**Verifier should independently confirm:**

1. `pytest -q` → 22 green (or current count) from a clean venv.
2. Two demo runs → identical health + component scores + experiment metric triples (not necessarily full `report_json` hash until ISSUE-004 resolved).
3. Report GET after completion: **`status` field** (expect ISSUE-001 until fixed).
4. No “ChatGPT ranking” / “Perplexity SERP” / “official AI share of voice” in report JSON blob.
5. `ScoreComponent` for `health` breakdown lists only the five readiness components (no mention/citation keys).
6. OpenAPI path matrix: `/health`, `POST/GET /api/v1/jobs`, `/report`, `/pages` with 202/200/404/409 as sketched.

**Next slice candidates (priority):**

1. Fix ISSUE-001 (report status) — small, high leverage.
2. Resolve ISSUE-002 (400 vs 422) + tighten D006 wording (ISSUE-004).
3. Clamp crawl timeout (ISSUE-005); split demo vs fallback findings (ISSUE-003).
4. Optional: live crawl smoke against a polite public site; live provider skipped-without-key already covered.
5. Verifier sign-off doc superseding `BASELINE-2026-09-18.md` (scaffold-era FAIL).

---

## Appendix — pytest

```
cd /workspace/aeo-mvp && .venv/bin/pytest -q
......................                                                   [100%]
22 passed, 2 warnings in 0.58s
```

Warnings: Starlette/httpx TestClient deprecation only — not product defects.

---

*End of ARCHITECT-REVIEW-SLICE1.md*
