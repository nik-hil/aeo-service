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
uvicorn aeo_mvp.api.app:app --host 127.0.0.1 --port 8000
```

Liveness: `GET http://127.0.0.1:8000/health`

## Demo job (no API keys / no network crawl)

```bash
curl -s -X POST http://127.0.0.1:8000/api/v1/jobs \
  -H 'Content-Type: application/json' \
  -d '{"url":"https://demo.example/","demo_mode":true,"options":{"provider":"demo"}}'
```

Poll status, then fetch the report:

```bash
JOB_ID=<id from create response>
curl -s http://127.0.0.1:8000/api/v1/jobs/$JOB_ID
curl -s http://127.0.0.1:8000/api/v1/jobs/$JOB_ID/report | python -m json.tool
curl -s http://127.0.0.1:8000/api/v1/jobs/$JOB_ID/pages
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

Under `provider=auto` / `AEO_VISIBILITY_PROVIDER=auto`: DO key → DigitalOcean web_search;
else OpenAI key → LLM mention; else DemoProvider. Demo mode always stays deterministic.

## Docs

- `docs/blueprint/BLUEPRINT.md` — product & technical blueprint
- `docs/methodology/METRICS.md` — `health-v1` formulas
- `docs/methodology/AI_VISIBILITY.md` — `vis-exp-v1` protocol
- `docs/methodology/RECOMMENDATIONS.md` — `rec-catalog-v1`
- `docs/api/openapi-sketch.yaml` — OpenAPI sketch
- `docs/IMPLEMENTATION_STATUS.md` — what works / gaps

## Example JSON

See `examples/` for sample create-job request and completed report.
