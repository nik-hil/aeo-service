# AEO MVP — Hashnode Markdown PoC

Small **Answer Engine Optimization** proof of concept for **Hashnode Markdown**.

**Core principle:** the LLM owns semantic intelligence (questions, full-document
question→section opportunities, recommended Markdown, quality eval). Python owns
plumbing (Markdown parse, JSON/schema validation, DO `web_search` visibility
metrics, DIFF, SUMMARY, safety). The introduction is not the default edit target.

```text
Hashnode Markdown
  → LLM question discovery + LLM quality pass (5–10)
    OR frozen prompt set (measurement mode; skips rediscovery)
  → OBSERVED AI-search visibility (DigitalOcean Responses + web_search)
    + optional competitor share
  → brand-fact / accuracy flags (LLM over OBSERVED vs CURRENT; branded/factual)
  → LLM opportunities + full RECOMMENDED.md
  → LLM quality evaluation
  → CURRENT.md / RECOMMENDED.md / DIFF / SUMMARY.md / VISIBILITY.md / report.json
  → Gradio report
```

Does **not** auto-publish. Visibility is an **API observation**, not consumer ChatGPT UI.

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
| `AEO_LLM_MODEL` | Default `openai-gpt-6-astra` (experiment) |
| `AEO_API_KEY` | Optional service auth (separate from LLM) |

Removed / not used: `OPENAI_API_KEY`, `DO_MODEL_ACCESS_KEY`, `MODEL_ACCESS_KEY`, `PERPLEXITY_API_KEY`.

### Model IDs (DO Inference catalog)

| Role | Model ID |
|------|----------|
| Default | `openai-gpt-6-astra` |
| Concise compare | `openai-gpt-5.6-luna` |

Wire via `AEO_LLM_MODEL` only. Confirm with `GET /v1/models` on your key if catalog names change. See [`docs/MODELS.md`](docs/MODELS.md).

## Live CLI (CoS / machine with key)

```bash
export AEO_LLM_API_KEY=...
export AEO_LLM_MODEL=openai-gpt-6-astra   # or openai-gpt-5.6-luna for compare
python -m aeo_mvp.cli path/to/article.md \
  --domain nik-hil.hashnode.dev \
  --live \
  --out docs/live-run/
```

### Measurement smoke (frozen prompts + competitors)

DigitalOcean `web_search` surface only — not ChatGPT / Perplexity UI:

```bash
export AEO_LLM_API_KEY=...
python -m aeo_mvp.cli examples/sample_article.md \
  --domain blog.example.com \
  --prompts-file examples/prompt_set_v1.json \
  --competitors-file examples/competitors_v1.json \
  --live \
  --out docs/live-measurement/
```

Writes `CURRENT.md`, `RECOMMENDED.md`, `DIFF.patch`, `SUMMARY.md`,
`VISIBILITY.md`, `report.json` (`llm_used`, `retrieval_used`, `model`, questions,
visibility + competitor_share, accuracy, opportunities, quality_eval).
`auto_publish` is always false.

`VISIBILITY.md` is the human-readable OBSERVED pack (rates, competitor share,
accuracy flags). `SUMMARY.md` stays the skimmable publish review.

See [`docs/PROMPT_SET.md`](docs/PROMPT_SET.md) and [`docs/VISIBILITY.md`](docs/VISIBILITY.md).

Dry visibility (still needs LLM for questions/recs unless `--prompts-file` + mocks):

```bash
python -m aeo_mvp.cli path/to/article.md --out out/   # no --live
```

## Gradio

```bash
python ui/gradio/app.py
```

Sections: ARTICLE · AI VISIBILITY (OBSERVED) · QUESTIONS · OPPORTUNITIES ·
BRAND-FACT / ACCURACY · CURRENT vs RECOMMENDED · DIFF · SUMMARY.md · QUALITY EVALUATION.

Controls: frozen prompts file path or paste; competitors list (`Name|domain`).

**User must run Gradio locally and visually accept UI changes before merge.**

## Tests

```bash
pytest -q
python -m compileall -q src ui
```

## Docs

- [`docs/ADR-001-llm-semantics.md`](docs/ADR-001-llm-semantics.md) — LLM vs Python ownership
- [`docs/OVERVIEW.md`](docs/OVERVIEW.md)
- [`docs/VISIBILITY.md`](docs/VISIBILITY.md)
- [`docs/PROMPT_SET.md`](docs/PROMPT_SET.md) — frozen prompts + competitors
- [`docs/MODELS.md`](docs/MODELS.md)
- [`docs/grok-bot-flow.md`](docs/grok-bot-flow.md) — Grok Bot cost/reliability flow playbook
- Cursor rules/skills under [`.cursor/`](.cursor/)
