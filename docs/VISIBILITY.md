# AI search visibility (DigitalOcean) — plumbing only

## Provider

DigitalOcean Inference **Responses API** + server-side **`web_search`**.

Auth: `AEO_LLM_API_KEY` only.

## Recorded per query (OBSERVED)

- query, answer, mention, citation, target-domain-in-sources
- exact target-page in sources / cited (when target URL configured)
- source URLs, citations, search_queries
- rates: mention, citation, target-in-sources, query_coverage
- optional **competitor share**: per competitor mention / citation / domain-in-sources

No semantic judgment of whether the question was “good” — that is LLM-owned upstream
(or supplied by a [frozen prompt set](PROMPT_SET.md)).

## Frozen prompts + competitors (measurement spine)

See [`PROMPT_SET.md`](PROMPT_SET.md). When `--prompts-file` / Gradio prompt controls
are set, visibility uses that list **instead of** LLM rediscovery.

Pack artifact `VISIBILITY.md` (alongside SUMMARY) holds human-readable OBSERVED
rates, competitor share, and brand-fact accuracy flags.

## Brand-fact / accuracy

For prompts with `kind` `branded` or `factual`, an LLM compares the OBSERVED
answer against CURRENT.md and flags conflicts with evidence quotes from both.
**LLM-GENERATED** flags only — not a world fact-check beyond DO answer + CURRENT.

## Flags

- `llm_used`: Responses HTTP call executed
- `retrieval_used`: web_search tool evidence present

## Not measured

Consumer ChatGPT / Gemini / Perplexity ranking UIs.

## Live smoke (optional, paid)

```bash
export AEO_LLM_API_KEY=...
python -m aeo_mvp.cli examples/sample_article.md \
  --domain blog.example.com \
  --prompts-file examples/prompt_set_v1.json \
  --competitors-file examples/competitors_v1.json \
  --live \
  --out docs/live-measurement/
```

Inspect `VISIBILITY.md` and `report.json` → `visibility` / `accuracy`.
