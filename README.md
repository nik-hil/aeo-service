# AEO MVP — Hashnode Markdown PoC

Small **Answer Engine Optimization** proof of concept for **Hashnode Markdown only**.

Flow:

```text
Hashnode Markdown
  → article understanding
  → topic-specific query discovery
  → AI-search visibility (DigitalOcean Responses + web_search)
  → opportunity analysis
  → grounded recommendations
  → CURRENT.md vs RECOMMENDED.md
  → Gradio report
```

Does **not** auto-publish to Hashnode or any CMS. Visibility is an **API observation**, not consumer ChatGPT / Gemini / Perplexity UI.

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev,ui]"
cp .env.example .env
```

## Environment

| Variable | Purpose |
|----------|---------|
| `AEO_LLM_API_KEY` | **Only** LLM credential (DigitalOcean Inference) |
| `AEO_LLM_BASE_URL` | Default `https://inference.do-ai.run/v1` |
| `AEO_LLM_MODEL` | Default `openai-gpt-4o` |
| `AEO_API_KEY` | Optional service auth (separate from LLM) |

Removed: `OPENAI_API_KEY`, `DO_MODEL_ACCESS_KEY`, `MODEL_ACCESS_KEY`, `PERPLEXITY_API_KEY`, and multi-key fallback chains.

## Run Gradio

```bash
source .venv/bin/activate
python ui/gradio/app.py
```

One screen: ARTICLE · AI VISIBILITY · OPPORTUNITIES · CURRENT vs RECOMMENDED · DIFF.

Dry-run is on by default (no live spend). Uncheck dry-run and set `AEO_LLM_API_KEY` for live DigitalOcean web_search.

## Run pipeline in Python

```python
from aeo_mvp import run_pipeline

report = run_pipeline("examples/sample_article.md", dry_run=True, write_artifacts_dir="out")
print(report.to_dict())
```

## Tests

```bash
pytest -q
python -m compileall -q src ui
```

Optional live DO test: set `AEO_LIVE_RETRIEVAL_TEST=true` and `AEO_LLM_API_KEY`.

## Package layout

```text
src/aeo_mvp/
  article.py           # load_hashnode_markdown
  markdown.py          # fence-aware H1–H6 sections
  queries.py           # article-specific discover_queries
  visibility.py        # DO Responses + web_search only
  recommendations.py   # opportunities + grounded recs
  llm.py               # thin client; llm_used / retrieval_used from execution
  pipeline.py          # obvious product flow
  config.py
ui/gradio/app.py       # thin UI
```

## Docs

- [`docs/OVERVIEW.md`](docs/OVERVIEW.md) — product flow and honesty limits
- [`docs/VISIBILITY.md`](docs/VISIBILITY.md) — DigitalOcean web_search notes
