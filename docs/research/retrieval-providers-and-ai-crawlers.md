# Retrieval-Enabled AI APIs & AI Crawler User-Agents

**Research date:** 2026-09-18 (IST / Asia/Calcutta)  
**Scope:** Official docs (2024–2026) for APIs an AEO product can use for *AI search visibility* experiments — not plain chat completion — plus authoritative crawler user-agent documentation.

**Critical framing for AEO:** Almost **no** developer API measures what consumers see in ChatGPT Search, Gemini Apps, Perplexity UI, or Copilot consumer UI. These APIs are **proxies** for retrieval-style answer generation with citations. Treat them as experimental visibility signals, not as rank-tracking for consumer AI UIs.

---

## Suggested AEO provider interface fields

Normalize every retrieval-capable provider adapter to:

| Field | Type | Meaning |
| --- | --- | --- |
| `retrieval_enabled` | `boolean` | Whether this call path performed (or was configured to perform) live/indexed web retrieval |
| `search_queries` | `string[]` | Queries the model/tool issued (when exposed) |
| `source_urls` | `string[]` | URLs consulted or returned as sources (broader than citations when available) |
| `citations` | `{url, title?, start_index?, end_index?, cited_text?}[]` | Inline or structured attributions tied to answer text |

Optional extras: `search_results` (snippets/titles), `consumer_ui_proxy: false`, `raw_tool_calls`.

---

## 1. OpenAI — Responses API / `web_search` / Chat Completions

**Official docs:**  
- https://developers.openai.com/api/docs/guides/tools-web-search  
- https://developers.openai.com/api/docs/guides/tools  
- Crawlers: https://developers.openai.com/api/docs/bots  

### Official capability: web retrieval

| Path | Retrieval |
| --- | --- |
| **Responses API** + `tools: [{ "type": "web_search" }]` | **YES** — hosted web search; model may choose to search (`tool_choice: "auto"`) or you can require it |
| **Chat Completions** + `gpt-5-search-api` + `web_search_options` | **YES** — specialized search model; docs say it **always** retrieves before answering |
| **Chat Completions without tools / without search models** (e.g. standard `gpt-4o`, `gpt-5` chat) | **NO** — no web retrieval; answers from model knowledge only |
| Legacy `web_search_preview` / `gpt-4o-search-preview` | Deprecated path; preview search models shutdown **2026-07-23** |

### What the API returns

- `web_search_call` items with `action` (`search` / `open_page` / `find_in_page`); search actions usually include `query` / queries  
- Message `annotations` of type `url_citation` (`url`, `title`, `start_index`, `end_index`)  
- Optional `include: ["web_search_call.action.sources"]` for full consulted URL list (broader than citations)  
- Optional `include: ["web_search_call.results"]` for raw results (incl. images)  
- Controls: `search_context_size`, domain `filters`, `user_location`, `external_web_access`, `return_token_budget`

### Measures consumer ChatGPT UI?

**NO.** API search is a developer product. ChatGPT consumer Search indexing/visibility is separately governed by **OAI-SearchBot** (see crawlers). Do not equate Responses `web_search` rankings with ChatGPT Search SERP.

### Auth / pricing (high level)

- Auth: `Authorization: Bearer $OPENAI_API_KEY`  
- Pricing: model token rates + **web search tool call charges** (commonly cited ~$10 / 1,000 searches; confirm on https://developers.openai.com/api/docs/pricing). Search-content tokens also count as model input.

### AEO interface mapping

```
retrieval_enabled: true  // when web_search tool used / search model used
search_queries:    web_search_call.action.query / queries
source_urls:       include sources + annotation urls
citations:         message.content[].annotations (url_citation)
```

For **llm_only** control: Chat Completions / Responses **without** `web_search` tool and without `*-search-*` models → `retrieval_enabled: false`.

---

## 2. Perplexity API — Sonar / Agent API (web search + citations)

**Official docs:**  
- https://docs.perplexity.ai/docs/sonar/models/sonar  
- https://docs.perplexity.ai/docs/sonar/models/sonar-pro  
- https://docs.perplexity.ai/api-reference/sonar-post  
- Agent migration: https://docs.perplexity.ai/docs/agent-api/migrate-from-sonar/overview  
- Crawlers: https://docs.perplexity.ai/docs/resources/perplexity-crawlers  

### Official capability: web retrieval

**YES** by default for Sonar / Sonar Pro (real-time web search).  
Sonar Chat Completions is migrating to **Agent API**; Sonar supported until **2026-09-27**. Agent API uses tools such as `{"type":"web_search"}`.  
API supports `disable_search` / search classifier options (Sonar OpenAPI) to force LLM-only behavior when needed.

### What the API returns

- Top-level `citations`: URL string array  
- `search_results`: `{title, url, date, last_updated, snippet, ...}`  
- Chat-completion-shaped `choices[].message.content`  
- Agent API: typed `output` with message + `search_results` item (citations move off top-level)

### Measures consumer Perplexity UI?

**NO.** Closest commercial proxy among vendors (same company, search-first product), but Sonar/Agent API ≠ consumer Perplexity.com ranking or UI layout.

### Auth / pricing (high level)

- Auth: `Authorization: Bearer <token>` → `https://api.perplexity.ai/v1/sonar`  
- Pricing example (Sonar): ~$1/1M input, $1/1M output, plus **per-1K-request** search context fees (Low/Medium/High, e.g. $5/$8/$12 per 1K) — see model pages

### AEO interface mapping

```
retrieval_enabled: true  // unless disable_search
search_queries:    often not explicitly returned as separate field on Sonar; may be null or derived
source_urls:       citations + search_results[].url
citations:         citations[] (+ search_results metadata)
```

---

## 3. Google Gemini — Grounding with Google Search

**Official docs:**  
- Interactions API: https://ai.google.dev/gemini-api/docs/google-search  
- generateContent (legacy surface): https://ai.google.dev/gemini-api/docs/generate-content/google-search  
- Vertex / Enterprise: https://docs.cloud.google.com/gemini-enterprise-agent-platform/models/grounding/grounding-with-google-search  

### Official capability: web retrieval

**YES** when `google_search` tool is enabled (`tools: [{"type":"google_search"}]` or `google_search: {}` in generateContent).  
Older models used `google_search_retrieval`; current models use `google_search`.  
Without the tool → **NO** web grounding (LLM-only).

### What the API returns

**Interactions API:**  
- `google_search_call.arguments.queries`  
- `google_search_result` (incl. required **search suggestions** HTML)  
- text `annotations` → `url_citation` (`url`, `title`, `start_index`, `end_index`)

**generateContent:**  
- `groundingMetadata.webSearchQueries`  
- `groundingChunks[].web.{uri,title}`  
- `groundingSupports` (segment ↔ chunk indices)  
- `searchEntryPoint.renderedContent` (Search Suggestions — **must display** per ToS when present)

### Measures consumer Gemini Apps UI?

**NO.** Grounding uses Google Search index paths for the **API/Vertex** product. Consumer Gemini Apps behavior and Google-Extended training/grounding controls are related but not the same measurement surface.

### Auth / pricing (high level)

- Gemini Developer API: `x-goog-api-key` / client SDK  
- Vertex: Google Cloud project + IAM  
- Billing: Gemini 3 — **per generated search query**; Gemini 2.5 and older — **per prompt** (see pricing page). Search Suggestions display obligations apply.

### AEO interface mapping

```
retrieval_enabled: true when google_search tool present and groundingMetadata / search steps exist
search_queries:    webSearchQueries / google_search_call.queries
source_urls:       groundingChunks.web.uri / url_citation.url
citations:         groundingSupports + chunks, or url_citation annotations
```

---

## 4. Anthropic Claude — Web search tool

**Official docs:**  
- https://platform.claude.com/docs/en/agents-and-tools/tool-use/web-search-tool  
- Server tools: https://platform.claude.com/docs/en/agents-and-tools/tool-use/server-tools  
- Pricing: https://docs.anthropic.com/en/docs/about-claude/pricing  
- Crawlers: https://support.claude.com/en/articles/8896518-does-anthropic-crawl-data-from-the-web-and-how-can-site-owners-block-the-crawler  

### Official capability: web retrieval

**YES** — server tool versions:  
- `web_search_20250305` (basic)  
- `web_search_20260209` (dynamic filtering)  
- `web_search_20260318` (response inclusion control)  

Also `web_fetch_*` for URL fetch. **Not available on Amazon Bedrock** (web search). Without the tool → **NO**.

### What the API returns

- `server_tool_use` with `input.query`  
- `web_search_tool_result` → `web_search_result` (`url`, `title`, `page_age`, `encrypted_content`)  
- Text blocks with `citations[]` (`web_search_result_location`: `url`, `title`, `cited_text`, `encrypted_index`)  
- `usage.server_tool_use.web_search_requests`

### Measures consumer Claude UI?

**NO.**

### Auth / pricing (high level)

- Auth: `x-api-key` + `anthropic-version`  
- Web search: **$10 per 1,000 searches** + standard token costs (search result content counts as input tokens)

### AEO interface mapping

```
retrieval_enabled: true when web_search tool invoked
search_queries:    server_tool_use.input.query
source_urls:       web_search_result.url (+ citation urls)
citations:         text.citations (web_search_result_location)
```

---

## 5. Microsoft Bing / Copilot APIs

**Official docs:**  
- Bing Search APIs **retired 2025-08-11**: https://learn.microsoft.com/en-us/lifecycle/announcements/bing-search-api-retirement  
- Replacement: Grounding with Bing Search (Azure AI Foundry Agents): https://learn.microsoft.com/en-us/azure/foundry/agents/how-to/tools/bing-tools  
- Product/pricing: https://www.microsoft.com/en-us/bing/apis  
- Azure OpenAI / Foundry also exposes OpenAI-style `web_search` on Responses (separate from Bing grounding): see Microsoft Learn “Web search with the Responses API”

### Official capability: web retrieval

| Product | Status |
| --- | --- |
| Classic Bing Search APIs (Web Search, News, etc.) | **Retired** (2025-08-11) — not for new AEO work |
| **Grounding with Bing Search** / Custom Search | **YES** — tool `bing_grounding` (or custom) via Foundry Agents / project connection |
| Consumer Microsoft Copilot UI | Not a public “measure my brand visibility” API |

### What the API returns

- Model-grounded answer with **`url_citation` annotations**  
- Per ToS: must display website URLs **and** Bing search query URL (rewrite endpoint to `www.bing.com/search?q=...`)  
- Developers do **not** get raw Bing SERP HTML; tool output is consumed server-side  
- Params: `count`, `market`, `set_lang`, `freshness`

### Measures consumer Copilot UI?

**NO.**

### Auth / pricing (high level)

- Azure subscription + Foundry project + Bing grounding resource + project connection; Entra auth for Agents  
- Pricing example: **$14 per 1,000 transactions** (Grounding with Bing Search / Custom Search plans)

### AEO interface mapping

```
retrieval_enabled: true when bing_grounding (or Foundry web search) used
search_queries:    from tool arguments / Bing query URL when exposed
source_urls:       annotation urls
citations:         url_citation annotations
```

---

## 6. Search backends (not consumer AI UIs): Tavily / Exa / SerpAPI

These are **search / retrieval APIs**. They do not measure ChatGPT/Gemini/Perplexity UI. Useful as (a) controlled SERP baselines, (b) DIY RAG for AEO experiments, (c) query expansion.

### Tavily — https://docs.tavily.com/documentation/api-reference/endpoint/search

| | |
| --- | --- |
| **Retrieval** | YES — `POST https://api.tavily.com/search` |
| **Returns** | `query`, `results[{title,url,content,score,...}]`, optional `answer`, images |
| **Consumer UI?** | NO |
| **Auth/pricing** | Bearer API key; credit-based (`basic`/`fast`/`ultra-fast` = 1 credit; `advanced` = 2) |
| **AEO fields** | `retrieval_enabled: true`, `search_queries: [query]`, `source_urls: results[].url`, `citations: results` (as evidence, not model inline cites) |

### Exa — https://exa.ai/docs/reference/search-api-guide

| | |
| --- | --- |
| **Retrieval** | YES — `POST https://api.exa.ai/search` (neural/keyword search + contents) |
| **Returns** | `results[{title,url,highlights,...}]`; optional `output` / `output.grounding` with structured synthesis |
| **Consumer UI?** | NO |
| **Auth/pricing** | Bearer / SDK API key; usage in `costDollars` |
| **AEO fields** | `retrieval_enabled: true`, `search_queries: [query]`, `source_urls: results[].url`, `citations: highlights + grounding` |

### SerpAPI — https://serpapi.com/search-api

| | |
| --- | --- |
| **Retrieval** | YES — scrapes Google (and other engines) SERPs as JSON |
| **Returns** | `organic_results[{title,link,snippet,...}]`, knowledge graph, related searches, etc. |
| **Consumer UI?** | NO (classic Google SERP proxy, not AI Overviews / AI Mode as a first-class “AI answer” product — treat as traditional search baseline) |
| **Auth/pricing** | `api_key` query param; plan-based search credits |
| **AEO fields** | `retrieval_enabled: true`, `search_queries: [q]`, `source_urls: organic_results[].link`, `citations: organic_results` |

---

## Provider comparison (AEO lens)

| Provider | Web retrieval API? | Citations / URLs | Search queries exposed? | Measures consumer AI UI? |
| --- | --- | --- | --- | --- |
| OpenAI Responses `web_search` | Yes | url_citation + sources | Usually yes | **No** |
| OpenAI Chat Completions (no search) | **No** | N/A | N/A | No |
| Perplexity Sonar/Agent | Yes | citations + search_results | Limited / varies | **No** (closest proxy) |
| Gemini `google_search` | Yes | annotations / groundingMetadata | **Yes** (`webSearchQueries`) | **No** |
| Claude `web_search_*` | Yes | citations + results | **Yes** (`input.query`) | **No** |
| Bing Grounding (Foundry) | Yes | url_citation + Bing query URL | Partial | **No** |
| Tavily / Exa / SerpAPI | Yes (search only) | Result URLs/snippets | Your query | **No** |

---

## AI crawler user-agents

Distinguish **training / foundation-model crawl**, **search/index crawl for AI answers**, and **user-initiated fetch**.

### OpenAI — https://developers.openai.com/api/docs/bots

| Agent | Purpose | Training vs retrieval | robots token |
| --- | --- | --- | --- |
| **GPTBot** | Crawl for generative AI **foundation model training** | **Training** | `GPTBot` |
| **OAI-SearchBot** | Index/surface sites in **ChatGPT search** results | **Search / retrieval index** | `OAI-SearchBot` |
| **ChatGPT-User** | User-triggered page visits (ChatGPT / Custom GPTs); not automatic crawl; robots.txt **may not apply** | **User-initiated retrieval** | `ChatGPT-User` |
| **OAI-AdsBot** | Ad landing-page validation | Ads / safety (not training) | `OAI-AdsBot` |

Settings are **independent** (allow SearchBot, disallow GPTBot, etc.). IP JSON: openai.com/gptbot.json, searchbot.json, chatgpt-user.json.

### Google — https://developers.google.com/crawling/docs/crawlers-fetchers/google-common-crawlers

| Agent / token | Purpose | Training vs retrieval | Notes |
| --- | --- | --- | --- |
| **Googlebot** | Google Search (and related Search surfaces) indexing | **Search** | Primary search crawler |
| **Google-Extended** | **Not a separate HTTP UA** — robots.txt **control token** for whether crawled content may be used for **Gemini training** and for **grounding** in Gemini Apps / Vertex Grounding with Google Search | **Training + API grounding control** | Does **not** affect Google Search ranking/inclusion |

### Anthropic — https://support.claude.com/en/articles/8896518-does-anthropic-crawl-data-from-the-web-and-how-can-site-owners-block-the-crawler (updated 2026-04-07)

| Agent | Purpose | Training vs retrieval |
| --- | --- | --- |
| **ClaudeBot** | Collect web content that may contribute to **model training** | **Training** |
| **Claude-SearchBot** | Navigate/index web to improve **search result quality** | **Search / retrieval index** |
| **Claude-User** | User-initiated fetches when people ask Claude questions | **User-initiated retrieval** |

Historical names **Claude-Web** / **Anthropic-AI** are superseded by the three agents above (prefer current Help Center). Honor `robots.txt`; support `Crawl-delay` for ClaudeBot.

### Perplexity — https://docs.perplexity.ai/docs/resources/perplexity-crawlers

| Agent | Purpose | Training vs retrieval |
| --- | --- | --- |
| **PerplexityBot** | Surface/link sites in Perplexity **search results**; **not** for foundation-model training | **Search / retrieval index** |
| **Perplexity-User** | User-triggered fetches for answers; **generally ignores robots.txt** | **User-initiated retrieval** |

### Common Crawl — https://commoncrawl.org/faq / https://commoncrawl.org/ccbot

| Agent | Purpose | Training vs retrieval |
| --- | --- | --- |
| **CCBot** | Open web crawl dataset for research; UA `CCBot/2.0 (https://commoncrawl.org/faq/)` | **Open dataset crawl** (widely reused for ML training by third parties; Common Crawl itself is a nonprofit dataset publisher) |

robots: `User-agent: CCBot` / `Disallow: /`. IP JSON: https://index.commoncrawl.org/ccbot.json.

### Bytespider (ByteDance / Toutiao)

| Agent | Purpose | Training vs retrieval |
| --- | --- | --- |
| **Bytespider** | ByteDance crawler associated with Toutiao Search / ByteDance data collection | Generally treated as **search + training data collection** for ByteDance products |

Authoritative primary docs are thinner than OpenAI/Google; publisher guidance commonly cites Toutiao webmaster materials (e.g. zhanzhang.toutiao.com) and UA token **`Bytespider`**. Industry reports of uneven robots.txt compliance → prefer WAF allow/deny with verified IPs if critical. Treat as **third-party AI/search crawler**, not a Western consumer ChatGPT/Gemini proxy.

---

## Implications for AEO MVP experiments

1. **Use retrieval-enabled APIs** (OpenAI `web_search`, Perplexity Sonar, Gemini grounding, Claude web_search, Bing grounding) to measure *whether and how* a brand/URL is cited in grounded answers.  
2. **Always run an LLM-only control** (same model family, no tools) to separate parametric memory from retrieval.  
3. **Never claim** API citation share equals ChatGPT/Gemini/Perplexity consumer UI share without a separate consumer-panel methodology.  
4. **Crawler policy** for publishers: allow **search bots** (OAI-SearchBot, PerplexityBot, Claude-SearchBot, Googlebot) if AI-search visibility is desired; separately decide **training** bots (GPTBot, ClaudeBot, Google-Extended, CCBot, Bytespider).  
5. **Search backends** (Tavily/Exa/SerpAPI) are for DIY pipelines and classic SERP baselines, not AI-UI measurement.

---

## Source index (primary)

1. OpenAI Web search — https://developers.openai.com/api/docs/guides/tools-web-search  
2. OpenAI Crawlers — https://developers.openai.com/api/docs/bots  
3. Perplexity Sonar — https://docs.perplexity.ai/docs/sonar/models/sonar  
4. Perplexity Crawlers — https://docs.perplexity.ai/docs/resources/perplexity-crawlers  
5. Gemini Grounding — https://ai.google.dev/gemini-api/docs/google-search  
6. Gemini generateContent grounding — https://ai.google.dev/gemini-api/docs/generate-content/google-search  
7. Google crawlers / Google-Extended — https://developers.google.com/crawling/docs/crawlers-fetchers/google-common-crawlers  
8. Anthropic Web search tool — https://platform.claude.com/docs/en/agents-and-tools/tool-use/web-search-tool  
9. Anthropic bots Help Center — https://support.claude.com/en/articles/8896518-does-anthropic-crawl-data-from-the-web-and-how-can-site-owners-block-the-crawler  
10. Bing Search API retirement — https://learn.microsoft.com/en-us/lifecycle/announcements/bing-search-api-retirement  
11. Grounding with Bing — https://learn.microsoft.com/en-us/azure/foundry/agents/how-to/tools/bing-tools  
12. Bing grounding product page — https://www.microsoft.com/en-us/bing/apis  
13. Tavily Search — https://docs.tavily.com/documentation/api-reference/endpoint/search  
14. Exa Search — https://exa.ai/docs/reference/search-api-guide  
15. SerpAPI Google Search — https://serpapi.com/search-api  
16. Common Crawl CCBot — https://commoncrawl.org/ccbot  
