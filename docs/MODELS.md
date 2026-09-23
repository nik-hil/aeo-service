# DigitalOcean Inference model IDs

Documented from the public [DO Inference models](https://docs.digitalocean.com/products/inference/details/models/) catalog (retrieved 2026-09-23). Confirm with an authenticated `GET https://inference.do-ai.run/v1/models` on the CoS box if names drift.

| Display name | Model ID (`AEO_LLM_MODEL`) | PoC role |
|--------------|----------------------------|----------|
| GPT-5.6 Luna | `openai-gpt-5.6-luna` | **Default experiment** |
| GPT-6 Astra | `openai-gpt-6-astra` | One-shot stronger compare |
| GPT-6 Luna | `openai-gpt-6-luna` | Available; not default here |
| GPT-4o | `openai-gpt-4o` | Legacy fallback if needed |

Set via env only — do not hardcode secrets:

```bash
export AEO_LLM_MODEL=openai-gpt-5.6-luna
# compare:
export AEO_LLM_MODEL=openai-gpt-6-astra
```
