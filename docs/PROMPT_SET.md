# Frozen prompt set (measurement spine)

Versioned JSON list of prompts used for **OBSERVED** DigitalOcean `web_search`
visibility **instead of** LLM query rediscovery.

## File format

```json
{
  "version": "1",
  "notes": "optional",
  "prompts": [
    {"id": "p1", "text": "What is an agent loop?", "kind": "factual"},
    {"id": "p2", "text": "Does Acme cover tool calling?", "kind": "branded"},
    "Plain string prompts default to kind general"
  ]
}
```

| Field | Required | Notes |
|-------|----------|-------|
| `version` | yes (default `"1"`) | String recorded in `report.json` |
| `prompts` | yes | Array of strings or objects |
| `text` / `prompt` / `question` | yes (objects) | 8–400 chars after normalize |
| `kind` | no | `general` (default), `branded`, or `factual` |
| `id` | no | Stable id; auto `pN` if omitted |

`kind` controls the brand-fact / accuracy pass: only `branded` and `factual`
prompts are compared (OBSERVED answer vs CURRENT.md).

## CLI

```bash
python -m aeo_mvp.cli examples/sample_article.md \
  --domain blog.example.com \
  --prompts-file examples/prompt_set_v1.json \
  --competitors-file examples/competitors_v1.json \
  --live \
  --out docs/live-measurement/
```

`--competitors` accepts `Name|domain` or `Name:domain` (comma or newline separated).

## Gradio

- **Frozen prompts file path** — path to JSON (wins over paste)
- **Frozen prompts paste** — JSON or one prompt per line; optional `factual:` / `branded:` prefix
- **Competitors** — `Name|domain` per line

## Competitors JSON

```json
{
  "competitors": [
    {"name": "Acme", "domain": "acme.com"}
  ]
}
```

## Honesty

Pack `VISIBILITY.md` + `report.json` metrics are **OBSERVED** DigitalOcean
Responses + `web_search` API results only — **not** ChatGPT / Gemini / Perplexity
consumer ranking UIs. Accuracy conflict flags are **LLM-GENERATED** over those
OBSERVED answers vs CURRENT.md (no invented world fact-check).
