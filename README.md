# AEO MVP

Backend-only **Answer Engine Optimization** service. Analyzes one public website per job for answer-engine readiness, computes a transparent **AEO Health Score** (`health-v1`), runs controlled visibility experiments (`vis-exp-v1`), and emits prioritized, evidence-linked recommendations as JSON.

> Visibility metrics are **sample estimates**, not rankings. This product does **not** reproduce ChatGPT / Gemini / Perplexity ranking.

## Stack

Python 3.11+, FastAPI, Pydantic v2, SQLAlchemy 2.x, SQLite, httpx, selectolax, pytest.

## Setup

```bash
cd /workspace/aeo-mvp
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

Copy `.env.example` to `.env` if you want local overrides (optional for demo).

## Run the API

```bash
source .venv/bin/activate
export AEO_API_KEY=dev-local-key-change-me
uvicorn aeo_mvp.api.app:app --host 127.0.0.1 --port 8000
```

Liveness (public): `GET http://127.0.0.1:8000/health`  
All other routes require `Authorization: Bearer $AEO_API_KEY` (see `docs/security/API_AUTH.md`).

## Demo job (no live provider keys / no network crawl)

```bash
curl -s -X POST http://127.0.0.1:8000/api/v1/jobs \
  -H "Authorization: Bearer $AEO_API_KEY" \
  -H 'Content-Type: application/json' \
  -d '{"url":"https://demo.example/","demo_mode":true,"options":{"provider":"demo"}}'
```

Poll status, then fetch the report:

```bash
JOB_ID=<id from create response>
curl -s -H "Authorization: Bearer $AEO_API_KEY" http://127.0.0.1:8000/api/v1/jobs/$JOB_ID
curl -s -H "Authorization: Bearer $AEO_API_KEY" http://127.0.0.1:8000/api/v1/jobs/$JOB_ID/report | python -m json.tool
curl -s -H "Authorization: Bearer $AEO_API_KEY" http://127.0.0.1:8000/api/v1/jobs/$JOB_ID/pages
```

Demo fixtures live under `src/aeo_mvp/demo/fixtures/` for fictional site `https://demo.example/`.

## Tests

```bash
source .venv/bin/activate
pytest -q
```

## Optional live visibility providers

**LLM mention** (`experiment_kind=llm_mention`): set `OPENAI_API_KEY` (optional
`OPENAI_BASE_URL`, `OPENAI_MODEL`). Chat completions only — **not** AI search visibility.

**AI search visibility** (`experiment_kind=ai_search_visibility`): set
`DO_MODEL_ACCESS_KEY` (or `MODEL_ACCESS_KEY`) and optionally
`AEO_VISIBILITY_PROVIDER=digitalocean_web_search`. Uses DigitalOcean Inference
Responses API + `web_search`. **Does not** measure consumer ChatGPT/Gemini/Perplexity UI
(`measures_consumer_ui=false`). See `docs/methodology/AI_SEARCH_VISIBILITY_DO.md`.

**Enable paid DO retrieval:** set `AEO_PAID_RETRIEVAL_OPT_IN=true` in the environment
(see `.env.example`). That is the runtime master switch. ADR-026 still applies:
paid retrieval runs only when opt-in **and** a ready QuerySet **and** DO credentials
(`DO_MODEL_ACCESS_KEY` / `MODEL_ACCESS_KEY`) are present. A DO key alone never spends.
API `options.paid_retrieval_opt_in=true` cannot bypass env false (fail-closed).

Under `provider=auto` / `AEO_VISIBILITY_PROVIDER=auto`: DigitalOcean web_search only when
a DO key is present **and** ADR-026 allows paid retrieval. Otherwise OpenAI key → LLM
mention; else DemoProvider. Demo mode always stays deterministic. See
`docs/architecture/ADR-026-paid-retrieval-opt-in.md`.

## Leadership UI

Optional Gradio demo for leadership walkthroughs (URL → AEO Health → gaps → recommendations → drafts). Does not change scoring or crawl security — it only calls the secured API.

```bash
pip install -e ".[ui]"
export AEO_API_KEY=dev-local-key-change-me
uvicorn aeo_mvp.api.app:app --host 127.0.0.1 --port 8000 &
export AEO_API_BASE_URL=http://127.0.0.1:8000
python ui/gradio/app.py
```

See [`ui/gradio/README.md`](ui/gradio/README.md) for modes, glossary, tests, and honesty limits.

## Docs

- `docs/blueprint/BLUEPRINT.md` — product & technical blueprint
- `docs/methodology/METRICS.md` — `health-v1` formulas
- `docs/methodology/AI_VISIBILITY.md` — `vis-exp-v1` protocol
- `docs/methodology/RECOMMENDATIONS.md` — `rec-catalog-v1`
- `docs/api/openapi-sketch.yaml` — OpenAPI sketch
- `docs/security/API_AUTH.md` — fail-closed API authentication (P0-3)
- `docs/IMPLEMENTATION_STATUS.md` — what works / gaps

## Example JSON

See `examples/` for sample create-job request and completed report.
