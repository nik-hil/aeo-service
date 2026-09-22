# PR #45 wiring fix: live path must call grounded_synth (NO MERGE)

Repo: https://github.com/nik-hil/aeo-service
Start from tip: f97543924e8aea959e59421aa7ff4a10b37cc469 on branch cursor/substantive-content-opt-e95e
Update draft PR #45. Do NOT merge. Do NOT touch main.

## Problem (proven live)
Paid dual run requested draft_paid=true + DO OpenAI-compatible key, but job reported:
- paid_llm=false, llm_used=false
- method like opt-draft-v1+paid_llm_stub_v0 / PaidLLMDraftGenerator stub
- only rewrite_introduction + metadata_seo_description applied
- rewrite_section / add_explanation ready=0 in live job (despite grounded_synth.py existing and unit/probe proving LLM can work)

## Required fix (NARROW)
Wire the REAL live content-optimization execution path so that when draft_paid=true AND a valid API key is present, it calls:
  grounded_synth → OpenAI-compatible chat completions → rewrite_section / add_explanation
  → claims + evidence_quote → entailment validation → ready ContentChangeOperation
  → Hashnode markdown_generator apply/validate only → recommended MD

MUST NOT route that path through PaidLLMDraftGenerator / paid_llm_stub / deterministic skeleton when opt-in+key are set.

PaidLLMDraftGenerator stub may remain for unrelated legacy draft behavior, but must not block grounded optimization.

## Fail-closed
Real LLM only if draft_paid=true AND valid key. Otherwise existing safe non-LLM behavior. Never log secrets.

## Reuse config
OPENAI_API_KEY / OPENAI_BASE_URL / OPENAI_MODEL and/or DO_MODEL_ACCESS_KEY / DO_INFERENCE_BASE_URL / DO_INFERENCE_MODEL. No new provider framework. No ChatGPT/Gemini. No ADR-026 / paid retrieval / SSRF / auth / job claim changes.

## Do NOT redesign
No new gap taxonomy, no more FAQ/HowTo promote rules, no Hashnode generator prose generation, no query-discovery redesign.

## Live acceptance (after fix)
HTML: https://nik-hil.hashnode.dev/agents-zero-to-hero-1-building-an-ai-agent-from-scratch-with-tool-calling
MD:   same + .md
draft_paid=true + real key. Do not publish.

HARD PASS requires:
- real LLM call (not stub)
- at least one rewrite_section OR add_explanation when eligible gap exists
- CURRENT != RECOMMENDED with substantive section change beyond intro-only
- claims grounded; #44 intro still works; HTML≈MD; tests green; freezes intact

If still intro+SEO only: FAIL and name first stage where section op was lost (gap selection → … → MD apply).

## Tests
Focused grounded_synth + Hashnode/content; full pytest with AEO_PAID_RETRIEVAL_OPT_IN=false clean env. Report counts.

## Deliver
Push to PR #45 draft. Report tip SHA, wiring change summary, dual live job ids, ops, diffs, claims, test counts, VERDICT fields for CoS. NO MERGE.
