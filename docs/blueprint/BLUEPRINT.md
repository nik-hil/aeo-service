# AEO MVP — Product & Technical Blueprint

**Product:** Backend-only Answer Engine Optimization (AEO) service  
**Location:** `/workspace/aeo-mvp`  
**Package:** `aeo_mvp` under `src/`  
**Formula version:** `health-v1` · **Experiment protocol:** `vis-exp-v1`  
**Date:** 2026-09-18 (IST)  
**Status:** Authoritative MVP blueprint — implement against this document

---

## 1. Product definition

**AEO MVP** is a greenfield, backend-only Python service that analyzes **one public website per job** for readiness to be extracted, understood, and cited by answer engines (AI Overviews, chat assistants with web retrieval, voice/snippet surfaces).

It produces:

1. **Crawl evidence** — HTML/pages fetched under documented caps, robots-respecting.
2. **Multi-pillar analysis** — technical accessibility, content extractability, entity clarity, structured data.
3. **Transparent AEO Health Score** (`health-v1`) — weighted mean of five 0–100 component scores with published formulas.
4. **Controlled AI visibility experiments** (`vis-exp-v1`) — pluggable providers; DemoProvider for deterministic demos; optional OpenAI-compatible live calls when credentials exist.
5. **Prioritized recommendations** — evidence-linked, impact×effort scored, site-owned fixes only.
6. **Machine-readable JSON report** — via FastAPI under `/api/v1`.

**What it is not:** multi-engine rank tracker, ChatGPT/Gemini/Perplexity ranking reproducer, frontend, auth/billing/multi-tenant SaaS, or production deploy target.

**Data provenance labels (mandatory on every metric/field where applicable):**

| Label | Meaning |
| --- | --- |
| `api_observation` | Raw or lightly parsed result from a provider API call |
| `derived_metric` | Computed from crawl/analysis evidence with a published formula |
| `llm_assessment` | Judgment produced by an LLM (optional path) |
| `estimate` | Sample statistic from finite experiment runs (not a census) |
| `synthetic_demo` | Fixture/seeded data from DemoProvider or demo crawl |

Never claim experiments reproduce proprietary answer-engine ranking.

---

## 2. User / job-to-be-done

**Primary user:** SEO/content engineer, growth marketer, or agency analyst who needs an auditable “is this site answer-engine ready?” artifact without a UI.

**Jobs (from research):**

1. Confirm site eligibility (bots can fetch HTML; not blocked; not JS-only for AI crawlers).
2. Diagnose why pages would not be quoted (structure, schema, entity, claim clarity).
3. Get one explainable AEO Health Score with transparent components.
4. Prioritize high-impact, site-owned fixes.
5. Run controlled, disclosed visibility experiments on fixed prompts.
6. Prove readiness/progress via machine-readable reports.
7. Avoid false confidence (readiness ≠ engine ranking).
8. Integrate via JSON API (no frontend required).

**Success for a job:** `status=completed`, persisted report with score breakdown, findings, recommendations, experiment rates (or demo equivalents), and methodology versions.

---

## 3. MVP feature list

### In scope

| # | Feature | Notes |
| --- | --- | --- |
| F1 | Job create + lifecycle | Statuses: `pending`, `crawling`, `analyzing`, `scoring`, `experimenting`, `synthesizing`, `completed`, `failed` |
| F2 | Same-host crawl | Max 25 pages, depth ≤ 2, robots.txt, 5s timeout, UA `AEOBot/0.1 (+research; respectful)` |
| F3 | Technical analyzer | HTTP status, robots/AI-bot directives, canonicals, meta robots, JS-risk heuristics, title/description presence |
| F4 | Content extractability analyzer | Heading hierarchy, answer-first blocks, FAQ/Q&A shape, paragraph length, claim density heuristics |
| F5 | Entity analyzer | Brand/org naming consistency, Organization signals, contact/sameAs hints |
| F6 | Structured data analyzer | JSON-LD parse, type fit, `@id`/sameAs hygiene, validity flags |
| F7 | AEO Health Score | `health-v1` weighted mean (see §8 / METRICS.md) |
| F8 | Experiment prep + run | Versioned prompt set; DemoProvider always; OpenAICompatibleProvider if key present |
| F9 | Findings synthesis | Merge readiness evidence + experiment observations |
| F10 | Prioritized recommendations | Impact×effort; evidence IDs linked |
| F11 | JSON report + API | POST/GET jobs, report, pages, health |
| F12 | Demo mode | Fixtures for `https://demo.example/`; bit-stable scores |
| F13 | SQLite persistence | All pages, evidence, observations, reports |
| F14 | Observation storage | Every visibility run: engine/provider, query, timestamp, raw (if permitted), mention, citation, cited URLs, methodology |

### Explicitly out of MVP

Auth, billing, multi-tenancy, frontend, production deploy, continuous multi-engine monitoring, competitor SOV, CMS publish, content generation, consumer UI scraping, guaranteed inclusion claims.

---

## 4. Architecture

### Pipeline (authoritative)

```
create_job
  → discover_and_crawl
  → analyze_technical
  → analyze_content_extractability
  → analyze_entities
  → analyze_structured_data
  → compute_aeo_health
  → prepare_experiment
  → run_visibility_experiment
  → synthesize_findings
  → prioritize_recommendations
  → emit_report
```

Health is computed **before** experiments so readiness ≠ visibility. Recommendations merge both.

### Runtime topology

```
┌─────────────────────────────────────────────────────────┐
│  FastAPI app (`aeo_mvp.api`)  prefix /api/v1            │
│    POST /jobs  GET /jobs/{id}  GET .../report  .../pages│
│    GET /health (liveness, no /api/v1 prefix)            │
└───────────────────────┬─────────────────────────────────┘
                        │
┌───────────────────────▼─────────────────────────────────┐
│  JobOrchestrator (`aeo_mvp.pipeline`)                   │
│  Synchronous-in-process for MVP (BackgroundTasks OK)    │
└───┬─────────┬─────────┬─────────┬─────────┬─────────────┘
    │         │         │         │         │
 crawl    analyzers   scoring  visibility  report
 (httpx)  (selectolax + heuristics)  (providers)
    │         │         │         │         │
┌───▼─────────▼─────────▼─────────▼─────────▼─────────────┐
│  SQLAlchemy 2.x + SQLite (`aeo_mvp.db`)                 │
└─────────────────────────────────────────────────────────┘
```

### Demo vs live branches

| Step | Live | Demo (`demo_mode=true` or `AEO_DEMO_MODE=true`) |
| --- | --- | --- |
| Crawl | httpx fetch | Load fixtures from `src/aeo_mvp/demo/fixtures/` |
| Visibility | DemoProvider if no key; else OpenAICompatibleProvider | DemoProvider only |
| Scoring / recs / report | Identical code paths | Identical; provenance `synthetic_demo` where applicable |

### Config (env)

| Var | Default | Purpose |
| --- | --- | --- |
| `AEO_DEMO_MODE` | `false` | Force demo crawl + DemoProvider |
| `AEO_DATABASE_URL` | `sqlite:///./aeo_mvp.db` | SQLAlchemy URL |
| `OPENAI_API_KEY` | unset | Enables OpenAICompatibleProvider |
| `OPENAI_BASE_URL` | `https://api.openai.com/v1` | Compatible endpoint |
| `OPENAI_MODEL` | `gpt-4o-mini` | Model id for live experiments |
| `AEO_CRAWL_MAX_PAGES` | `25` | Hard cap |
| `AEO_CRAWL_MAX_DEPTH` | `2` | Hard cap |
| `AEO_CRAWL_TIMEOUT_S` | `5` | Per-request timeout |

---

## 5. Component boundaries

| Package / module | Responsibility | Must not |
| --- | --- | --- |
| `aeo_mvp.api` | HTTP schemas, routes, status codes | Crawl, score, or call LLMs directly |
| `aeo_mvp.pipeline` | JobOrchestrator; status transitions; step ordering | Know HTTP details or SQL dialects |
| `aeo_mvp.crawler` | robots, URL discovery, fetch, page store | Analyze content quality or score |
| `aeo_mvp.analyzers.technical` | Technical Accessibility evidence + score inputs | Call providers |
| `aeo_mvp.analyzers.content` | Content Readiness / Answerability inputs | Fetch network |
| `aeo_mvp.analyzers.entities` | Entity Clarity inputs | Fetch network |
| `aeo_mvp.analyzers.structured_data` | Structured Data inputs | Fetch network |
| `aeo_mvp.scoring` | `health-v1` aggregation | Re-crawl or invent evidence |
| `aeo_mvp.visibility` | `AIVisibilityProvider` protocol; Demo + OpenAICompatible | Mutate health formula |
| `aeo_mvp.recommendations` | Priority scoring; evidence linking | Change analyzer evidence |
| `aeo_mvp.report` | Assemble Report DTO from DB | Run pipeline steps |
| `aeo_mvp.demo` | Fixtures + seed helpers | Live network |
| `aeo_mvp.db` | Models, session, migrations-lite `create_all` | Business rules |
| `aeo_mvp.config` | Settings from env | Side effects beyond reading env |

**Provider interface (lock):**

```python
class AIVisibilityProvider(Protocol):
    name: str  # e.g. "demo", "openai_compatible"
    async def run_query(self, query: str, *, context: VisibilityContext) -> VisibilityObservation: ...
```

`DemoProvider` — deterministic; reads fixtures / seeded templates.  
`OpenAICompatibleProvider` — optional; chat completions; never claimed as ChatGPT consumer UI.

---

## 6. Database schema

SQLite via SQLAlchemy 2.x. UUIDs as strings. Timestamps UTC ISO-8601 stored as text or DateTime timezone-aware.

```sql
-- jobs
CREATE TABLE jobs (
  id TEXT PRIMARY KEY,                    -- uuid4
  base_url TEXT NOT NULL,
  demo_mode INTEGER NOT NULL DEFAULT 0,
  status TEXT NOT NULL,                   -- enum below
  options_json TEXT NOT NULL DEFAULT '{}',
  error_message TEXT,
  health_formula_version TEXT,            -- e.g. health-v1
  experiment_protocol_version TEXT,       -- e.g. vis-exp-v1
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  completed_at TEXT
);

-- pages (crawl artifacts)
CREATE TABLE pages (
  id TEXT PRIMARY KEY,
  job_id TEXT NOT NULL REFERENCES jobs(id),
  url TEXT NOT NULL,
  final_url TEXT,
  depth INTEGER NOT NULL,
  status_code INTEGER,
  content_type TEXT,
  fetched_at TEXT,
  html TEXT,                              -- may be truncated in future; store full for MVP
  title TEXT,
  robots_meta TEXT,
  canonical_url TEXT,
  fetch_error TEXT,
  UNIQUE(job_id, url)
);

-- analysis_evidence (one row per finding atom)
CREATE TABLE analysis_evidence (
  id TEXT PRIMARY KEY,
  job_id TEXT NOT NULL REFERENCES jobs(id),
  page_id TEXT REFERENCES pages(id),      -- null = site-level
  analyzer TEXT NOT NULL,                 -- technical|content|entities|structured_data
  code TEXT NOT NULL,                     -- e.g. TECH_ROBOTS_BLOCKED
  severity TEXT NOT NULL,                 -- info|low|medium|high
  message TEXT NOT NULL,
  data_json TEXT NOT NULL DEFAULT '{}',
  provenance TEXT NOT NULL,               -- derived_metric|api_observation|...
  created_at TEXT NOT NULL
);

-- score_components
CREATE TABLE score_components (
  id TEXT PRIMARY KEY,
  job_id TEXT NOT NULL REFERENCES jobs(id),
  component TEXT NOT NULL,                -- technical|content|entity|structured_data|answerability|health
  score REAL NOT NULL,                    -- 0..100
  formula_version TEXT NOT NULL,
  breakdown_json TEXT NOT NULL DEFAULT '{}',
  provenance TEXT NOT NULL DEFAULT 'derived_metric',
  UNIQUE(job_id, component, formula_version)
);

-- experiment_configs
CREATE TABLE experiment_configs (
  id TEXT PRIMARY KEY,
  job_id TEXT NOT NULL REFERENCES jobs(id),
  protocol_version TEXT NOT NULL,         -- vis-exp-v1
  provider_name TEXT NOT NULL,
  model_id TEXT,
  prompt_set_id TEXT NOT NULL,
  prompts_json TEXT NOT NULL,             -- list of {id, query, intent}
  runs_per_prompt INTEGER NOT NULL,
  created_at TEXT NOT NULL
);

-- visibility_observations (EVERY run stored)
CREATE TABLE visibility_observations (
  id TEXT PRIMARY KEY,
  job_id TEXT NOT NULL REFERENCES jobs(id),
  experiment_config_id TEXT NOT NULL REFERENCES experiment_configs(id),
  provider_name TEXT NOT NULL,
  engine_label TEXT NOT NULL,             -- display label; not a claim of consumer UI
  query TEXT NOT NULL,
  prompt_id TEXT NOT NULL,
  run_index INTEGER NOT NULL,             -- 0..N-1
  observed_at TEXT NOT NULL,
  raw_response TEXT,                      -- null if provider forbids storage
  raw_storage_permitted INTEGER NOT NULL DEFAULT 1,
  detected_mention INTEGER NOT NULL,      -- 0/1
  detected_citation INTEGER NOT NULL,     -- 0/1
  cited_urls_json TEXT NOT NULL DEFAULT '[]',
  extraction_methodology TEXT NOT NULL,   -- e.g. vis-exp-v1:mention-rule-v1
  provenance TEXT NOT NULL,               -- api_observation|synthetic_demo|estimate
  meta_json TEXT NOT NULL DEFAULT '{}'
);

-- experiment_metrics (aggregates)
CREATE TABLE experiment_metrics (
  id TEXT PRIMARY KEY,
  job_id TEXT NOT NULL REFERENCES jobs(id),
  metric_name TEXT NOT NULL,              -- ai_mention_rate|ai_citation_rate|query_coverage
  value REAL NOT NULL,
  numerator INTEGER NOT NULL,
  denominator INTEGER NOT NULL,
  provenance TEXT NOT NULL DEFAULT 'estimate',
  protocol_version TEXT NOT NULL,
  UNIQUE(job_id, metric_name, protocol_version)
);

-- findings
CREATE TABLE findings (
  id TEXT PRIMARY KEY,
  job_id TEXT NOT NULL REFERENCES jobs(id),
  category TEXT NOT NULL,                 -- readiness|visibility|meta
  title TEXT NOT NULL,
  summary TEXT NOT NULL,
  evidence_ids_json TEXT NOT NULL DEFAULT '[]',
  observation_ids_json TEXT NOT NULL DEFAULT '[]',
  severity TEXT NOT NULL
);

-- recommendations
CREATE TABLE recommendations (
  id TEXT PRIMARY KEY,
  job_id TEXT NOT NULL REFERENCES jobs(id),
  code TEXT NOT NULL,
  title TEXT NOT NULL,
  rationale TEXT NOT NULL,
  effort TEXT NOT NULL,                    -- S|M|L
  impact REAL NOT NULL,                   -- 0..1
  priority_score REAL NOT NULL,
  evidence_ids_json TEXT NOT NULL DEFAULT '[]',
  finding_ids_json TEXT NOT NULL DEFAULT '[]',
  rank INTEGER NOT NULL
);

-- reports
CREATE TABLE reports (
  id TEXT PRIMARY KEY,
  job_id TEXT NOT NULL UNIQUE REFERENCES jobs(id),
  report_json TEXT NOT NULL,              -- full Report DTO
  emitted_at TEXT NOT NULL
);
```

**Job status enum:** `pending` | `crawling` | `analyzing` | `scoring` | `experimenting` | `synthesizing` | `completed` | `failed`

---

## 7. API specification

Base path for job resources: `/api/v1`. Liveness: `GET /health` (no version prefix).

### Endpoints

| Method | Path | Purpose |
| --- | --- | --- |
| `POST` | `/api/v1/jobs` | Create job; start pipeline |
| `GET` | `/api/v1/jobs/{id}` | Job status + score summary if available |
| `GET` | `/api/v1/jobs/{id}/report` | Full machine-readable report |
| `GET` | `/api/v1/jobs/{id}/pages` | Crawled pages list |
| `GET` | `/health` | Liveness `{ "status": "ok" }` |

### Request / response sketches (Pydantic-shaped)

**POST `/api/v1/jobs`**

```json
// Request
{
  "url": "https://example.com/",
  "demo_mode": false,
  "options": {
    "max_pages": 25,
    "max_depth": 2,
    "runs_per_prompt": 3,
    "provider": "auto"
  }
}

// Response 202
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "base_url": "https://example.com/",
  "status": "pending",
  "demo_mode": false,
  "created_at": "2026-09-18T04:30:00+00:00",
  "links": {
    "self": "/api/v1/jobs/550e8400-e29b-41d4-a716-446655440000",
    "report": "/api/v1/jobs/550e8400-e29b-41d4-a716-446655440000/report",
    "pages": "/api/v1/jobs/550e8400-e29b-41d4-a716-446655440000/pages"
  }
}
```

`provider`: `auto` | `demo` | `openai_compatible`. `auto` → demo if no API key or `demo_mode`, else openai_compatible when key present, else demo with note.

**GET `/api/v1/jobs/{id}`**

```json
{
  "id": "...",
  "base_url": "https://example.com/",
  "status": "completed",
  "demo_mode": false,
  "error_message": null,
  "health_score": 72.4,
  "health_formula_version": "health-v1",
  "experiment_protocol_version": "vis-exp-v1",
  "component_scores": {
    "technical": 80.0,
    "content": 70.0,
    "entity": 65.0,
    "structured_data": 55.0,
    "answerability": 75.0
  },
  "created_at": "...",
  "updated_at": "...",
  "completed_at": "..."
}
```

**GET `/api/v1/jobs/{id}/report`** — see Report shape in §11 / emitted by `emit_report`. Includes `caveats`, `methodology`, `scores`, `findings`, `recommendations`, `experiment`, `provenance` map.

**GET `/api/v1/jobs/{id}/pages`**

```json
{
  "job_id": "...",
  "count": 12,
  "pages": [
    {
      "id": "...",
      "url": "https://example.com/",
      "final_url": "https://example.com/",
      "depth": 0,
      "status_code": 200,
      "title": "Example",
      "fetch_error": null
    }
  ]
}
```

**Errors:** `404` unknown job; `400` invalid URL / non-http(s); `409` report requested while not `completed` (or return partial with status — MVP: `409` until completed/failed); `500` unexpected.

Full OpenAPI sketch: `docs/api/openapi-sketch.yaml`.

---

## 8. Metric definitions and formulas

Authoritative detail: `docs/methodology/METRICS.md` (`formula_version: health-v1`).

### Summary

| Metric | Type | Formula (summary) |
| --- | --- | --- |
| **Technical Accessibility Score** \(T\) | derived 0–100 | Mean of check passes weighted (robots allow, 2xx homepage, canonical present, no noindex on key pages, low JS-risk, title present) — see METRICS.md |
| **Content Readiness Score** \(C\) | derived 0–100 | Heading quality + answer-first presence + FAQ/Q&A shape + usable paragraph ratio |
| **Entity Clarity Score** \(E\) | derived 0–100 | Brand consistency + Organization signal + contact/sameAs hints |
| **Structured Data Score** \(S\) | derived 0–100 | JSON-LD presence + parse validity + type fit + `@id`/sameAs hygiene |
| **Answerability Score** \(A\) | derived 0–100 | Overlap of extractable Q→passage pairs + definition/howto blocks (content-derived) |
| **AEO Health Score** \(H\) | derived 0–100 | \(H = 0.25T + 0.25C + 0.20E + 0.15S + 0.15A\) |
| **AI Mention Rate** | estimate | `#runs with detected_mention` / `#runs` |
| **AI Citation Rate** | estimate | `#runs with detected_citation` / `#runs` |
| **Query Coverage** | estimate | `#prompts with ≥1 mention` / `#prompts` |
| **Recommendation Priority** | derived | `impact × effort_weight` (see RECOMMENDATIONS.md) |

All health components clamped to `[0, 100]`. Round display to 1 decimal; store full float.

---

## 9. AI visibility experiment methodology

Authoritative detail: `docs/methodology/AI_VISIBILITY.md` (`protocol_version: vis-exp-v1`).

**Principles:**

1. Experiments are **samples**, not rankings.
2. API ≠ consumer ChatGPT/Gemini/Perplexity UI.
3. Store every observation with methodology tag.
4. Separate **mention** vs **citation** vs recommendation language.
5. Demo and live share the same schema; differ only in provenance.

**Default prompt set (`prompt-set-v1`):** 5 prompts (brand, category, comparison-neutral, problem/solution, “best for X”), `runs_per_prompt=3` → 15 observations.

**Mention rule:** case-insensitive match of brand/org tokens (from entity analysis or hostname) in response text.  
**Citation rule:** any URL whose registrable domain matches the job’s site domain appears in cited_urls or in markdown/link-like spans in raw text.

---

## 10. Recommendation methodology

Authoritative detail: `docs/methodology/RECOMMENDATIONS.md`.

Every recommendation must:

- Reference ≥1 `analysis_evidence.id` and/or `visibility_observations.id`
- Include `effort` ∈ {S, M, L} and `impact` ∈ [0, 1]
- Compute `priority_score = impact × effort_weight` where S=1.0, M=0.7, L=0.4
- Rank descending by `priority_score`, tie-break by severity then code

Catalog of recommendation codes is fixed in RECOMMENDATIONS.md (e.g. `REC_ADD_JSONLD_ORG`, `REC_FIX_ROBOTS_AI_BOTS`, …).

---

## 11. Demo-mode design

**Trigger:** `demo_mode=true` on job create, or `AEO_DEMO_MODE=true`, or `options.provider=demo`.

**Site:** fictional `https://demo.example/` (never fetched live).

**Fixtures path:** `src/aeo_mvp/demo/fixtures/`

```
fixtures/
  site_map.json          # urls, depth, titles
  pages/
    index.html
    about.html
    pricing.html
    blog-aeo-basics.html
    faq.html
  robots.txt
  visibility/
    prompt_set.json
    observations.json    # fixed 15 runs
```

**Invariants:**

- Same inputs → identical Health Score and recommendation ranks (bit-stable within float formatting).
- All visibility rows `provenance=synthetic_demo`.
- Report includes `"demo_mode": true` and caveats stating data is synthetic.

---

## 12. Test strategy

| Layer | Tool | Coverage targets |
| --- | --- | --- |
| Unit | pytest | Scoring formulas, mention/citation rules, recommendation priority, URL same-host filter, robots parse |
| Analyzer | pytest + fixture HTML | Each analyzer on demo fixtures; golden evidence codes |
| Pipeline | pytest | Status transitions; demo job end-to-end → completed report |
| API | httpx AsyncClient + FastAPI | POST job, poll, get report/pages/health |
| Contract | compare report keys | Required top-level keys always present |
| Regression | snapshot | Demo report score components within ±0.1 |

**Mandatory tests before “feature complete” (Verifier):**

1. Demo e2e: create → completed → health present → recommendations ≥1 → observations = prompts×runs.
2. Health formula unit: known component vector → exact H.
3. Live provider skipped cleanly when no API key (no crash).
4. Crawl respects max_pages and same-host.
5. Provenance fields never blank on metrics.

---

## 13. Independent verification strategy

AEO Verifier (separate agent/role) must:

1. Re-read METRICS.md and recompute Health from a completed job’s `score_components.breakdown_json` independently.
2. Confirm observation count = `len(prompts) * runs_per_prompt`.
3. Confirm no API copy claims “ChatGPT ranking” / “Perplexity SERP” in report strings.
4. Spot-check 3 recommendations have non-empty evidence IDs existing in DB.
5. Run `pytest` green.
6. Sign off in `docs/verification/` with date and checklist.

Engineers must not self-certify “complete” without Verifier note.

---

## 14. Repository structure

```
/workspace/aeo-mvp/
  DECISIONS.md
  README.md                 # later / minimal
  pyproject.toml            # package aeo_mvp
  src/
    aeo_mvp/
      __init__.py
      config.py
      main.py               # FastAPI app factory
      api/
        __init__.py
        routes.py
        schemas.py
      db/
        __init__.py
        models.py
        session.py
      crawler/
        __init__.py
        robots.py
        fetch.py
        discover.py
      analyzers/
        __init__.py
        technical.py
        content.py
        entities.py
        structured_data.py
        base.py
      scoring/
        __init__.py
        health.py           # health-v1
      visibility/
        __init__.py
        base.py             # Protocol
        demo.py
        openai_compatible.py
        metrics.py          # mention/citation rates
      recommendations/
        __init__.py
        engine.py
        catalog.py
      pipeline/
        __init__.py
        orchestrator.py
      report/
        __init__.py
        builder.py
      demo/
        __init__.py
        loader.py
        fixtures/
          ...
  tests/
    unit/
    integration/
    fixtures/
  docs/
    blueprint/BLUEPRINT.md
    methodology/METRICS.md
    methodology/AI_VISIBILITY.md
    methodology/RECOMMENDATIONS.md
    api/openapi-sketch.yaml
    research/...
    verification/
  examples/
  scripts/
```

---

## 15. Implementation plan (phased)

### Phase 0 — Scaffold
- `pyproject.toml`, package `aeo_mvp`, config, DB session, empty FastAPI app, `GET /health`.
- Decision docs already present; ensure imports work: `python -c "import aeo_mvp"`.

### Phase 1 — Crawl + persist
- Models: `Job`, `Page`.
- Crawler: robots, same-host, depth 2, max 25, timeout 5s, UA locked.
- `POST /api/v1/jobs` + `GET /api/v1/jobs/{id}` + `GET .../pages`.
- Demo fixture crawl path.

### Phase 2 — Analyzers
- Four analyzers writing `analysis_evidence`.
- Unit tests on fixture HTML.

### Phase 3 — Scoring
- Implement `health-v1` in `scoring/health.py`.
- Persist `score_components`; expose on job GET.

### Phase 4 — Recommendations
- Catalog + priority engine; persist `recommendations` + `findings` (readiness-only first).

### Phase 5 — AI visibility
- `AIVisibilityProvider`, `DemoProvider`, optional `OpenAICompatibleProvider`.
- `prepare_experiment` + `run_visibility_experiment` + experiment metrics.
- Merge visibility into findings/recommendations.

### Phase 6 — API polish + demo
- `GET .../report` full DTO; OpenAPI alignment; demo bit-stability; caveats object.

### Phase 7 — Tests + verify
- Full pytest suite; Verifier checklist; fix gaps; freeze `health-v1` / `vis-exp-v1` strings.

**Dependency rule:** Do not start Phase N+1 until Phase N leaves DB + API in a coherent state (job can sit at the last completed status without corruption).

---

## Report DTO (emit_report target)

```json
{
  "job_id": "...",
  "base_url": "...",
  "demo_mode": false,
  "status": "completed",
  "methodology": {
    "health_formula_version": "health-v1",
    "experiment_protocol_version": "vis-exp-v1",
    "prompt_set_id": "prompt-set-v1",
    "crawl": {
      "max_pages": 25,
      "max_depth": 2,
      "user_agent": "AEOBot/0.1 (+research; respectful)"
    }
  },
  "caveats": [
    "AI visibility metrics are sample estimates from controlled experiments, not engine rankings.",
    "API-based observations are not equivalent to consumer ChatGPT/Gemini/Perplexity UI results.",
    "This product does not reproduce proprietary answer-engine ranking."
  ],
  "scores": {
    "aeo_health": { "value": 72.4, "provenance": "derived_metric", "formula_version": "health-v1" },
    "technical": { "value": 80.0, "provenance": "derived_metric" },
    "content": { "value": 70.0, "provenance": "derived_metric" },
    "entity": { "value": 65.0, "provenance": "derived_metric" },
    "structured_data": { "value": 55.0, "provenance": "derived_metric" },
    "answerability": { "value": 75.0, "provenance": "derived_metric" }
  },
  "experiment": {
    "provider_name": "demo",
    "ai_mention_rate": { "value": 0.4, "numerator": 6, "denominator": 15, "provenance": "estimate" },
    "ai_citation_rate": { "value": 0.2, "numerator": 3, "denominator": 15, "provenance": "estimate" },
    "query_coverage": { "value": 0.6, "numerator": 3, "denominator": 5, "provenance": "estimate" },
    "observations_count": 15
  },
  "findings": [],
  "recommendations": [],
  "pages_crawled": 12,
  "emitted_at": "..."
}
```

---

*End of BLUEPRINT.md — implement against this document and the methodology siblings.*
