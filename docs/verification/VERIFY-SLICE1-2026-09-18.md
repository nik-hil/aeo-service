# AEO MVP Slice-1 Independent Verification

**Date:** 2026-09-18 10:26:44 IST  
**Verifier:** Independent AEO Verifier executor (re-ran all checks; did not trust Engineering claims)  
**Repo:** `/workspace/aeo-mvp`  
**DB used:** isolated `sqlite:////tmp/aeo_verify_slice1.db` via `AEO_DATABASE_URL` (did not write to Engineering `aeo_mvp.db`)  
**Server:** `AEO_DEMO_MODE=true` uvicorn on `127.0.0.1:8000`

## Overall verdict: **PASS**

All six acceptance criteria PASS.

| # | Criterion | Result |
| --- | --- | --- |
| 1 | Demo-mode E2E | **PASS** |
| 2 | Metric formulas (health-v1 weights) | **PASS** |
| 3 | Determinism (two demo runs) | **PASS** |
| 4 | pytest | **PASS** (22 passed) |
| 5 | Honesty (no ranking-reproduction claims) | **PASS** |
| 6 | Observations storage | **PASS** |

---

## 1. Demo-mode E2E — PASS

### Commands

```bash
# freed port 8000, then:
cd /workspace/aeo-mvp
rm -f /tmp/aeo_verify_slice1.db
AEO_DEMO_MODE=true AEO_DATABASE_URL="sqlite:////tmp/aeo_verify_slice1.db" \
  .venv/bin/uvicorn aeo_mvp.api.app:app --host 127.0.0.1 --port 8000

curl -s http://127.0.0.1:8000/health
# -> HTTP 200 {"status":"ok"}

curl -s -X POST http://127.0.0.1:8000/api/v1/jobs \
  -H 'Content-Type: application/json' \
  --data-binary @examples/create_job_demo.json
# -> HTTP 202, id=acf8d249-43b6-4a96-8fc4-7815cd37228e (run1); id=cc7ad5c6-00d1-4a36-94bd-93f5a0b2963a (run2)

# poll GET /api/v1/jobs/{id} until status=completed
curl -s http://127.0.0.1:8000/api/v1/jobs/acf8d249-43b6-4a96-8fc4-7815cd37228e/report
# -> HTTP 200
```

### Evidence (report required sections)

Report top-level keys include: `scores`, `findings`, `recommendations`, `experiment`, `methodology`, `caveats`.

- **Health breakdown** (`scores`): technical=100.0, content=57.5, entity=92.5, structured_data=100.0, answerability=100.0, **aeo_health=87.9** (`formula_version=health-v1`)
- **Findings:** 4 items (evidence-linked readiness/visibility findings)
- **Recommendations:** 5 items (keys include `code`, `priority_score`, `evidence_ids`, `rationale`)
- **Visibility metrics** (`experiment`): `ai_mention_rate.value=0.4` (6/15), `ai_citation_rate.value≈0.1333` (2/15), `query_coverage.value=0.6` (3/5), `provider_name=demo`, `observations_count=15`

Job GET after completion (run1): `status=completed`, `health_score=87.9`, component_scores present.

### Minor note (non-blocking)

Persisted report JSON field `status` was `"synthesizing"` while job row / `GET /jobs/{id}` correctly showed `completed`. Report payload itself was complete (scores/findings/recs/experiment present). Likely report snapshot written before final status flip — defect for Engineering, does **not** fail criterion 1.

---

## 2. Metric formulas — PASS

### Doc (`docs/methodology/METRICS.md`)

- Lines 29–33 (weights table): Technical **0.25**, Content **0.25**, Entity **0.20**, Structured Data **0.15**, Answerability **0.15**
- Line 42: `H = clamp(0.25 T + 0.25 C + 0.20 E + 0.15 S + 0.15 A)`

### Code (`src/aeo_mvp/scoring/health.py`)

```text
WEIGHTS = {
    "technical": 0.25,       # L15
    "content": 0.25,         # L16
    "entity": 0.20,          # L17
    "structured_data": 0.15, # L18
    "answerability": 0.15,   # L19
}
```

`health_from_components` (L35–39) multiplies the same WEIGHTS. Exact match to METRICS.md health-v1: **0.25 / 0.25 / 0.20 / 0.15 / 0.15**.

---

## 3. Determinism — PASS

Two independent POSTs of identical `examples/create_job_demo.json`:

| Field | Run1 (`acf8d249-43b6-4a96-8fc4-7815cd37228e`) | Run2 (`cc7ad5c6-00d1-4a36-94bd-93f5a0b2963a`) |
| --- | --- | --- |
| `scores.aeo_health.value` | **87.9** | **87.9** |
| `experiment.ai_mention_rate.value` | **0.4** | **0.4** |
| `experiment.ai_citation_rate.value` | **0.13333333333333333** | **0.13333333333333333** |
| `experiment.query_coverage.value` | **0.6** | **0.6** |

Full `scores` objects and mention/citation/query_coverage metrics identical across runs.

---

## 4. pytest — PASS

```bash
cd /workspace/aeo-mvp
.venv/bin/python -m pytest -q
```

Output snippet:

```text
......................                                                   [100%]
22 passed, 2 warnings in 0.55s
```

Actual count: **22 passed** (matches expectation). Warnings: Starlette/httpx TestClient deprecation only.

---

## 5. Honesty — PASS

Grep of README, docs, examples, report caveats, and source for ChatGPT/Gemini/Perplexity ranking language:

- README L5: product does **not** reproduce ChatGPT / Gemini / Perplexity ranking; metrics are sample estimates.
- Report caveats (live demo runs): explicitly deny proprietary ranking reproduction; label API ≠ consumer UI; demo fixtures are synthetic.
- `docs/methodology/AI_VISIBILITY.md` L17 / L22–24: **Must not** use “ChatGPT ranking” / “Perplexity SERP” language (prohibition, not a product claim).
- No affirmative claim that the product reproduces ChatGPT/Gemini/Perplexity ranking was found.

Language is honest: controlled observations / demo / estimates / not proprietary ranking.

---

## 6. Observations storage — PASS

### DB (`visibility_observations` in isolated verify DB)

Columns include: `provider_name`, `query`, `detected_mention`, `detected_citation`, `cited_urls_json`, `extraction_methodology`, `provenance`.

Sample row:

```text
provider_name='demo'
query='What is AcmeFlow?'
detected_mention=1
detected_citation=1
cited_urls_json='["https://demo.example/", "https://demo.example/about"]'
extraction_methodology='vis-exp-v1:mention-rule-v1+citation-rule-v1'
provenance='synthetic_demo'
```

Count after two jobs: **30** observations (15 per job). Model: `src/aeo_mvp/db/models.py` `VisibilityObservation` (L150–171).

### API

No dedicated `/observations` route (404). Report exposes aggregates (`observations_count`, rates, `provider_name`) and methodology tags; criterion allows API **and/or** DB — DB storage satisfies.

---

## Defects / notes for Engineering (non-blocking)

1. Report JSON `status` may freeze as `"synthesizing"` even when job completes — align snapshot timing with final job status.
2. No public API to list raw observations (DB-only); consider read endpoint if product needs auditability without SQLite access.
3. pytest emits 2 Starlette/httpx TestClient deprecation warnings (dependency hygiene).

## Cleanup

Verifier killed the uvicorn process on port 8000 after evidence collection. Product source was not modified.
