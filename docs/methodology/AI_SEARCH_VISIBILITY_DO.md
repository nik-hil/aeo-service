# AI Search Visibility — DigitalOcean Web Search Provider

**protocol:** `ai-search-vis-v1`  
**provider_id:** `digitalocean_web_search`  
**Date:** 2026-09-18  
**Status:** Phase 2 MVP retrieval provider

---

## What this measures

Controlled **AI search visibility** experiments via the DigitalOcean Inference
**Responses API** with the built-in **`web_search`** tool (third-party search
backend: Exa.ai per DO docs).

Each run records:

| Field | Source |
| --- | --- |
| `search_queries` | `web_search_call.action.queries` / `query` |
| `source_urls` | tool sources/results + citation URLs |
| `citations` | message `annotations` with `type=url_citation` |
| `target_domain_appeared` | target registrable domain in `source_urls` (PSL) |
| `target_domain_cited` | target domain in **structured** `url_citation` annotations only |
| `detected_mention` | brand-token mention rule on answer text |

**Provenance:** `api_observation` for rows; aggregate rates use `estimate`.

---

## What this does **not** measure

- Consumer **ChatGPT / Gemini / Perplexity** UI rankings or SERP positions
  (`measures_consumer_ui=false`).
- LLM-only chat completions without retrieval (`llm_mention` is a separate
  experiment kind).
- Guaranteed “share of voice” or proprietary answer-engine ranking.

Do **not** market these rates as “ChatGPT ranking” or “Perplexity SERP.”

---

## Metrics (`ai-search-vis-v1`)

Let \(R\) = observation runs, \(P\) = distinct prompts.

| Metric | Formula | Notes |
| --- | --- | --- |
| `ai_search_mention_rate` | \(M / R\) | Brand mention in answer text |
| `ai_search_citation_rate` | \(K / R\) | Structured `url_citation` to target domain |
| `target_domain_appearance_rate` | \(A / R\) | Target domain in sources/results |
| `query_coverage` | \(Q_c / P\) | Prompts with ≥1 mention **or** appearance **or** citation |

These keys are emitted **only** for `experiment_kind=ai_search_visibility`.
`llm_mention_rate` / `llm_url_mention_rate` stay on non-retrieval runs.

Competitor domains from sources are **descriptive co-appearance counts only** —
no winner ranking.

---

## Configuration

| Env | Default | Purpose |
| --- | --- | --- |
| `DO_MODEL_ACCESS_KEY` | — | Preferred auth (required for live) |
| `MODEL_ACCESS_KEY` | — | Fallback name from DO docs |
| `DO_INFERENCE_BASE_URL` | `https://inference.do-ai.run/v1` | API base |
| `DO_INFERENCE_MODEL` | `openai-gpt-4o` | Documented working model; also try `openai-gpt-oss-20b` |
| `DO_WEB_SEARCH_MAX_USES` | `3` | Clamped 1–5 |
| `DO_WEB_SEARCH_MAX_RESULTS` | `5` | Clamped 1–10 |
| `DO_INFERENCE_TIMEOUT_S` | `60` | HTTP timeout |
| `AEO_VISIBILITY_PROVIDER` | `auto` | `digitalocean_web_search` \| `openai_compatible` \| `demo` \| `auto` |

**Selection:** demo mode always uses `DemoProvider`. Otherwise
`provider=digitalocean_web_search` / `AEO_VISIBILITY_PROVIDER=digitalocean_web_search`
requires a DO key. Under `auto`, a present DO key selects this provider before
OpenAI-compatible LLM mention.

Primary prompt set for live non-demo runs: **discovered queries** (top N from
`AEO_QUERY_TOP_N`), not only the fixed `prompt-set-v1` templates.

---

## Failure policy

Missing key, HTTP errors, or responses without web_search evidence → **explicit
error** (`DigitalOceanWebSearchError`). Never fabricate retrieval results or
silently fall back to LLM-only while claiming `ai_search_visibility`.

---

## Live validation (follow-up)

Optional pytest live gate:

```bash
DO_MODEL_ACCESS_KEY=... AEO_LIVE_RETRIEVAL_TEST=true pytest -q tests/unit/test_digitalocean_web_search.py -k live
```

Default CI/`pytest` does **not** call the paid API. Hashnode (or other) live
retrieval validation is a follow-up on a machine that has
`DO_MODEL_ACCESS_KEY`.

---

## Official DO references

- https://docs.digitalocean.com/products/inference/how-to/use-server-side-tools/use-web-search/
- https://docs.digitalocean.com/products/inference/how-to/use-responses-api/
- Base: `https://inference.do-ai.run/v1` · `POST /v1/responses`
