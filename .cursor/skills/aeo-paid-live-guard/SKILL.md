---
name: aeo-paid-live-guard
description: Use when adding, calling, or documenting paid LLM / web_search / Astra live paths.
---
# Paid live guard

## Rules
1. Default path = dry / fixture / mock.
2. Paid calls only behind explicit opt-in (`--live`, `AEO_LIVE_RETRIEVAL_TEST`). Document the flag in PR body.
3. No silent retries that re-bill.
4. Keys: `AEO_LLM_API_KEY` only; never commit, log, or paste into reports.
5. Cursor cloud agent VMs often lack paid keys — keep CI and PR demos green without them.
6. Set `llm_used` / `retrieval_used` from real execution evidence only.

## PR checklist
- [ ] Tests pass without live keys
- [ ] Live steps listed as optional / manual
- [ ] No new multi-provider key fallbacks
