# Blueprint Addendum — External Review Fixes (2026-09-18)

This addendum **revises** BLUEPRINT.md / methodology without rewriting the product.
Supersedes conflicting language that framed chat-completions mention/citation rates as “AI search visibility.”

## A1. Experiment kinds (P0)

Two distinct experiment kinds:

| Kind | `experiment_kind` | Requires `retrieval_enabled` | Metrics naming |
| --- | --- | --- | --- |
| LLM mention experiment | `llm_mention` | **false** | `llm_mention_rate`, `llm_url_mention_rate` (text/URL heuristics in model output) |
| AI search visibility experiment | `ai_search_visibility` | **true** | `ai_search_mention_rate`, `ai_search_citation_rate`, `target_domain_appearance_rate` |

**Forbidden:** labeling OpenAI-compatible `/chat/completions` (no tools) results as AI search visibility.

Protocol versions:
- `llm-mention-v1` — non-retrieval LLM probes
- `ai-search-vis-v1` — retrieval-enabled providers only
- Legacy `vis-exp-v1` reports must add `experiment_kind` + `retrieval_enabled` when re-emitted; keep raw rows.

## A2. Provider capabilities (P0)

Every provider exposes:

```python
class ProviderCapabilities(BaseModel):
    provider_id: str
    retrieval_enabled: bool
    experiment_kinds: list[Literal["llm_mention", "ai_search_visibility"]]
    returns_search_queries: bool
    returns_source_urls: bool
    returns_citations: bool
    measures_consumer_ui: bool  # almost always False
    notes: str
```

`OpenAICompatibleProvider` / `DemoProvider` (fixture chat): `retrieval_enabled=False`, kinds=`[llm_mention]`.
Future: `PerplexitySonarProvider`, `GeminiGroundingProvider`, etc. with `retrieval_enabled=True`.

## A3. Observation schema extensions (P0, DB-compatible)

Add columns (nullable for back-compat) on `visibility_observations` / DTO:

- `model_id`
- `retrieval_enabled` (int 0/1)
- `experiment_kind`
- `search_queries_json`
- `source_urls_json`
- `target_domain_appeared` (int)
- `target_domain_cited` (int)

`experiment_configs` gains: `experiment_kind`, `retrieval_enabled`.

Report `experiment` object must include these fields and never use the key `ai_mention_rate` for non-retrieval providers (use `llm_mention_rate`).

## A4. SSRF security model (P0)

Crawler URL allow policy (`aeo_mvp.security.ssrf`):

1. Scheme must be `http` or `https` only.
2. Hostname must not be `localhost` / `*.localhost`.
3. Resolve DNS → all A/AAAA; every address must be **global unicast public** (reject loopback, RFC1918, link-local, multicast, reserved, IPv4-mapped private, metadata `169.254.169.254`, IPv6 ULA `fc00::/7`, etc.).
4. Connect only to validated IPs (pin host header); max redirects = 5; **re-validate** each redirect Location the same way.
5. Block DNS rebinding: re-resolve before each hop; reject if any new address is non-public.
6. Demo mode does not fetch live URLs (fixtures only).

Documented in `docs/security/SSRF.md`.

## A5. Independent verification (P0)

Verifier produces `docs/verification/VERIFY-COMPLETE-*.md` by running the API, demo job, (optional) real-site job, recomputing health, checking provenance labels, SSRF tests, failure cases. Pytest green is necessary but not sufficient.

## A6–A10. P1 summary (implement after P0)

- **AI crawler analysis:** per-agent robots/meta for OAI-SearchBot, GPTBot, Google-Extended, ClaudeBot, PerplexityBot — report purpose separately; never claim allow ⇒ visibility.
- **Site understanding:** infer brand/products/topics/audience/category from crawl; persist with provenance.
- **Query discovery:** generate/classify/dedupe/select queries from site understanding; persist set.
- **Competitors:** only from retrieval-enabled experiments; descriptive aggregates, no winner ranking.
- **Recommendations:** enrich with URL, evidence, problem, action, pattern, validation; no ranking promises.
- **Report:** add `executive_summary` + `page_findings`; keep machine-readable report.

## A11. health-v1

Keep `health-v1` immutable. Publish signal classification table in `docs/methodology/SIGNAL_CLASSIFICATION.md`. Material methodology changes → `health-v2` later.


## P1 implementation note (2026-09-18)

Implemented against existing architecture (no rewrite):

- `ai_crawler_access` — robots/meta per documented agent; **never** allow ⇒ visibility
- `site_understanding` — deterministic HTML/JSON-LD; optional LLM flag default **off**
- `discovered_queries` — classify/dedupe/select; demo experiments still use `prompt-set-v1` fixtures for bit-stability
- Retrieval: `RetrievalEnabledVisibilityProvider` + `PerplexitySonarProvider` stub (raises / skips; no fake AI-search metrics)
- Competitors: only when `retrieval_enabled`
- Recommendations enriched; report adds `executive_summary` + `page_findings`
- `docs/methodology/SIGNAL_CLASSIFICATION.md` — health-v1 immutable
