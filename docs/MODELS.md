# DigitalOcean Inference model IDs

Documented from the public [DO Inference models](https://docs.digitalocean.com/products/inference/details/models/) catalog. Confirm with an authenticated `GET https://inference.do-ai.run/v1/models` on the CoS box if names drift.

| Display name | Model ID (`AEO_LLM_MODEL`) | PoC role |
|--------------|----------------------------|----------|
| GPT-6 Astra | `openai-gpt-6-astra` | **Default** (post CoS live acceptance 2026-09-23) |
| GPT-5.6 Luna | `openai-gpt-5.6-luna` | Concise alternative / compare |
| GPT-6 Luna | `openai-gpt-6-luna` | Catalog-available; not used in acceptance |
| GPT-4o | `openai-gpt-4o` | Legacy fallback if needed |

## Why Astra is default

Same Safari fixture + domain, paid live on tip `ee076e1` (CoS Astra vs Luna acceptance):

- **Astra:** 9 structured opportunities with valid target headings; usable RECOMMENDED.md.
- **Luna:** 0 opportunities + stray `---` in RECOMMENDED despite `quality_eval` pass.
- **Both:** `llm_used` / `retrieval_used` true; 5–10 article-specific questions (no heading transforms); no Direct-answer spam; quality eval pass; `auto_publish=false`.

Luna remains documented for cheaper/concise compare runs via `AEO_LLM_MODEL`. Fresh `docs/live-*` artifacts are produced by CoS after recommendation-prompt upgrades (older live folders are not kept on the branch).

```bash
export AEO_LLM_MODEL=openai-gpt-6-astra
# compare:
export AEO_LLM_MODEL=openai-gpt-5.6-luna
```
