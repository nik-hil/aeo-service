# AI search visibility (DigitalOcean) — plumbing only

## Provider

DigitalOcean Inference **Responses API** + server-side **`web_search`**.

Auth: `AEO_LLM_API_KEY` only.

## Recorded per query (OBSERVED)

- query, answer, mention, citation, target-domain-in-sources
- source URLs, citations, search_queries
- rates: mention, citation, target-in-sources, query_coverage

No semantic judgment of whether the question was “good” — that is LLM-owned upstream.

## Flags

- `llm_used`: Responses HTTP call executed
- `retrieval_used`: web_search tool evidence present

## Not measured

Consumer ChatGPT / Gemini / Perplexity ranking UIs.
