# AI search visibility (DigitalOcean)

## Provider

DigitalOcean Inference **Responses API** with the server-side **`web_search`** tool.

Auth: `AEO_LLM_API_KEY` only (base URL / model via `AEO_LLM_BASE_URL`, `AEO_LLM_MODEL`).

## What is recorded per query

- query text
- model answer
- mention (brand/title tokens in answer, or target domain in sources)
- citation (target domain in structured citation URLs)
- target-domain-in-sources
- source URLs + citation objects
- aggregate mention / citation / target-in-sources rates

## Flags

- `llm_used`: true only after a successful Responses HTTP call
- `retrieval_used`: true only when the response contained web_search tool evidence (`web_search_call`, search queries, sources, or citations)

Config alone never sets these flags.

## Not measured

Consumer ChatGPT, Gemini, or Perplexity ranking UIs.
