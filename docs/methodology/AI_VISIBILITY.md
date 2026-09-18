# AEO MVP — AI Visibility Experiment Protocol

**protocol_version:** `vis-exp-v1`  
**Date:** 2026-09-18 (IST)  
**Status:** Authoritative for MVP visibility experiments

---

## 1. Purpose and honesty rules

This protocol defines how the AEO MVP runs **controlled AI visibility experiments** and stores observations.

**Must:**

- Treat all rates as **sample estimates**, not census rankings.
- Label API results as **API observations**, not consumer UI truth.
- Never claim reproduction of ChatGPT, Gemini, Perplexity, Claude, or Copilot **ranking**.
- Store every run (success or structured failure) with methodology tags.
- Distinguish **mention** vs **citation**.
- Work with **zero** live credentials via `DemoProvider`.

**Must not:**

- Use language: “ChatGPT ranking”, “Perplexity SERP”, “official AI share of voice”, “guaranteed citations”.
- Scrape consumer chat UIs in MVP.
- Fold visibility rates into AEO Health Score (`health-v1`).

**Preferred language:** visibility experiment, sample rate, observed mention/citation in run, methodology version, estimate.

---

## 2. Pipeline placement

```
... → compute_aeo_health → prepare_experiment → run_visibility_experiment → synthesize_findings → ...
```

`prepare_experiment` freezes config. `run_visibility_experiment` writes `visibility_observations` then aggregates `experiment_metrics`.

---

## 3. Providers

### Interface

```python
class VisibilityContext(BaseModel):
    job_id: str
    base_url: str
    brand_tokens: list[str]          # from entity analysis + hostname
    site_registrable_domain: str     # e.g. example.com
    prompt_id: str
    run_index: int
    protocol_version: str = "vis-exp-v1"

class VisibilityObservation(BaseModel):
    provider_name: str
    engine_label: str
    query: str
    prompt_id: str
    run_index: int
    observed_at: datetime
    raw_response: str | None
    raw_storage_permitted: bool
    detected_mention: bool
    detected_citation: bool
    cited_urls: list[str]
    extraction_methodology: str
    provenance: Literal["api_observation", "synthetic_demo", "estimate"]
    meta: dict[str, Any] = {}

class AIVisibilityProvider(Protocol):
    name: str
    async def run_query(self, query: str, *, context: VisibilityContext) -> VisibilityObservation: ...
```

### DemoProvider

- `name = "demo"`
- Reads `src/aeo_mvp/demo/fixtures/visibility/observations.json` keyed by `(prompt_id, run_index)` or generates deterministic text from seeded templates.
- `provenance = synthetic_demo`
- `engine_label = "demo-engine"`
- Always available; used when `demo_mode`, `provider=demo`, or no live credentials under `provider=auto`.

### OpenAICompatibleProvider

- `name = "openai_compatible"`
- Requires `OPENAI_API_KEY` (optional `OPENAI_BASE_URL`, `OPENAI_MODEL`).
- Calls chat completions with a **fixed system prompt** (below).
- `provenance = api_observation` on raw row; aggregated rates use `estimate`.
- `engine_label = f"openai_compatible:{model_id}"`
- **Caveat string attached to every live report:** API responses are not equivalent to consumer ChatGPT/Gemini/Perplexity UI.

**System prompt (lock for vis-exp-v1 live):**

```
You are a research assistant answering factual questions for an offline evaluation.
Answer helpfully in 2–4 short paragraphs. If you reference websites, include full https URLs.
Do not claim to browse unless URLs are provided in the user message.
```

**User message:** the prompt query only (optionally append `Context site: {base_url}` — MVP **does** append one line `Site under evaluation: {base_url}` so the model has a referent; this is disclosed in methodology).

If the HTTP call fails: store observation with `raw_response` = error string, `detected_mention=false`, `detected_citation=false`, `meta.error=true`; still counts in denominator.

---

## 4. Prompt set (`prompt-set-v1`)

Default \(P = 5\), \(N = 3\) → \(R = 15\).

| prompt_id | intent | Template (substitute `{brand}`, `{category}`, `{domain}`) |
| --- | --- | --- |
| `ps1_brand` | brand | `What is {brand}?` |
| `ps2_category` | category | `What are leading options for {category}?` |
| `ps3_compare` | comparison-neutral | `How do teams evaluate tools in {category}?` |
| `ps4_problem` | problem/solution | `How can a website improve its chances of being cited in AI answers?` |
| `ps5_best` | best-for | `What is a good resource for answer engine optimization on {domain}?` |

**Derivation of slots:**

- `{domain}` = registrable domain of job `base_url`
- `{brand}` = top brand token from entity analysis, else domain label (e.g. `example` from `example.com`)
- `{category}` = from job `options.category` if provided, else default `"answer engine optimization"` for non-demo; demo fixtures fix category to `"project management software"` for the fictional site narrative

Prompt set JSON is copied verbatim into `experiment_configs.prompts_json` at prepare time (frozen).

---

## 5. Observation schema (storage)

Every run → one `visibility_observations` row:

| Field | Rule |
| --- | --- |
| `provider_name` | `demo` or `openai_compatible` |
| `engine_label` | See providers |
| `query` | Exact string sent |
| `prompt_id` | From prompt set |
| `run_index` | `0 .. N-1` |
| `observed_at` | UTC timestamp |
| `raw_response` | Full text if `raw_storage_permitted` else null |
| `raw_storage_permitted` | Default true; set false only if provider policy requires |
| `detected_mention` | Mention rule below |
| `detected_citation` | Citation rule below |
| `cited_urls_json` | Extracted URL list |
| `extraction_methodology` | `vis-exp-v1:mention-rule-v1` + citation tag |
| `provenance` | `synthetic_demo` \| `api_observation` |
| `meta_json` | model, latency_ms, error flags, token usage if known |

**extraction_methodology values:**

- Mentions: `vis-exp-v1:mention-rule-v1`
- Combined field stored as: `vis-exp-v1:mention-rule-v1+citation-rule-v1`

---

## 6. Mention vs citation rules

### Mention rule (`mention-rule-v1`)

1. Build `brand_tokens`: unique casefolded strings from entity brand candidates + registrable domain label (hostname without TLD) + full registrable domain.
2. Tokens shorter than 3 chars ignored (except if brand_tokens would become empty — then keep domain label).
3. `detected_mention = true` iff any token appears as a **whole-word** case-insensitive match in `raw_response` (regex `\b{re.escape(token)}\b` with Unicode letter boundaries best-effort; for domain with dots, match substring case-insensitive).
4. Mentions in URLs alone do **not** count as mention unless the display text also matches (avoid false positives from forced `Site under evaluation` line — **exclude** the appended context line from the match corpus before testing).

### Citation rule (`citation-rule-v1`)

1. Extract URLs via regex on `raw_response` plus any provider-structured citation list in `meta`.
2. Normalize to absolute https URLs where possible.
3. `detected_citation = true` iff any extracted URL’s registrable domain equals `site_registrable_domain` (ignore `www.`).
4. `cited_urls` = list of those matching URLs (unique, order preserved).

**Mention ≠ citation:** a run may mention without citing, cite without a textual brand token (rare), both, or neither. Never collapse into one boolean in the API.

---

## 7. Aggregate metrics

After all runs:

| Metric | Formula | provenance |
| --- | --- | --- |
| AI Mention Rate | \(M / R\) | `estimate` or `synthetic_demo` |
| AI Citation Rate | \(K / R\) | same |
| Query Coverage | \(Q_m / P\) | same |

Persist in `experiment_metrics` with numerators/denominators.

Report must include \(P\), \(N\), \(R\), provider, model_id, protocol_version, prompt_set_id.

---

## 8. Demo vs live matrix

| Aspect | Demo | Live (OpenAI-compatible) |
| --- | --- | --- |
| Network | None | HTTPS to base URL |
| Crawl | Fixtures `https://demo.example/` | Real site |
| Observations | Fixed JSON / seeded | API calls ×15 |
| Provenance | `synthetic_demo` | `api_observation` → rates `estimate` |
| Stability | Bit-stable | Stochastic; rates may vary |
| Credentials | None | `OPENAI_API_KEY` |

`provider=auto` selection:

1. If `demo_mode` or `AEO_DEMO_MODE` → DemoProvider  
2. Else if key present and provider not forced demo → OpenAICompatibleProvider  
3. Else → DemoProvider + finding note `VIS_FALLBACK_DEMO_NO_CREDENTIALS`

---

## 9. Caveats object (required on every report)

```json
[
  "AI visibility metrics are sample estimates from controlled experiments (protocol vis-exp-v1), not engine rankings.",
  "API-based observations are not equivalent to consumer ChatGPT, Gemini, or Perplexity UI results.",
  "This product does not reproduce proprietary answer-engine ranking or retrieval.",
  "Model or provider updates can change results; compare only runs that share protocol_version, prompt_set_id, provider, and model_id."
]
```

Demo adds: `"This job used synthetic demo fixtures; visibility data is not from a live model."`

---

## 10. Failure handling

| Failure | Behavior |
| --- | --- |
| Single run HTTP 429/5xx | Retry once after 1s; then store error observation |
| All runs fail | Job continues; rates may be 0; finding `VIS_ALL_RUNS_FAILED` |
| Provider misconfigured | Fall back to demo only if `auto`; else fail job at experimenting with clear error |
| Raw storage disabled | Persist null raw; still store booleans and cited_urls |

---

## 11. Versioning

Any change to mention/citation rules, prompt templates, system prompt, or default \(N\) requires a new `protocol_version` (e.g. `vis-exp-v2`). Keep `vis-exp-v1` immutable once Phase 5 ships tests.

---

*End of AI_VISIBILITY.md*
