# Failures — live-astra-20260923-090147

**Status:** FAILED (no CURRENT/RECOMMENDED/DIFF artifacts written)  
**Model:** `openai-gpt-6-astra`  
**Tip SHA:** `0cec9d3faf0bf7e0ca30aaed58f2b911c9c0f89c`  
**URI:** https://nik-hil.hashnode.dev/agents-zero-to-hero-12-building-ai-subagents-with-context-isolation.md  
**Domain:** `nik-hil.hashnode.dev`

## What failed

`generate_recommendations` raised after exhausting the internal repair loop
(`MAX_RECOMMENDATION_ATTEMPTS = 3`). Outer runner used `--rec-retries 1`, so there
was no outer redraw after the internal loop failed.

## Final validator error (raised)

```
RECOMMENDED has substantive section edits without matching opportunities for: ['Agents Zero to Hero #12: Building AI Subagents with Context Isolation']. Emit an opportunity for each applied section change, or leave that section unchanged.
```

### Mismatched section

- `Agents Zero to Hero #12: Building AI Subagents with Context Isolation` (title/H1)

Astra applied a substantive edit to that section in RECOMMENDED without emitting a matching opportunity (or should have left the section unchanged).

## Repair loop (what was sent back to Astra)

Same tip path as Luna:

| Attempt | Prompt | Known outcome |
|---|---|---|
| 1 | Base recommend prompt (CURRENT = original article) | Validation failed (exact intermediate error **not persisted**) |
| 2 | Base + `REPAIR FEEDBACK` with exact prior validator error | Validation failed again (intermediate error **not persisted**) |
| 3 | Base + second-repair `REPAIR FEEDBACK` with latest error | Failed with the final error above → raised `LLMError` |

Recommendations phase ~356.3s is consistent with multiple internal LLM calls before the final raise.

**Guarantees that held:** failed RECOMMENDED never became CURRENT; validation failures (not transport blips) drove the repair feedback path.

**Caveat:** only the **final** raised `LLMError` is recorded on disk.

## Timings

| Phase | Elapsed |
|---|---|
| Questions | 45.9s (9 questions) |
| Visibility | 306.2s (`retrieval_used=true`) |
| Recommendations (all internal attempts) | ~356.3s then fail |

## Related

- Pack README: [README.md](./README.md)
- Compare (Luna vs Astra): [../live-astra-vs-luna-z2h12-20260923.md](../live-astra-vs-luna-z2h12-20260923.md)
