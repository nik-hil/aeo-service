# Failures — live-luna-20260923-085557

**Status:** FAILED (no CURRENT/RECOMMENDED/DIFF artifacts written)  
**Model:** `openai-gpt-5.6-luna`  
**Tip SHA:** `0cec9d3faf0bf7e0ca30aaed58f2b911c9c0f89c`  
**URI:** https://nik-hil.hashnode.dev/agents-zero-to-hero-12-building-ai-subagents-with-context-isolation.md  
**Domain:** `nik-hil.hashnode.dev`

## What failed

`generate_recommendations` raised after exhausting the internal repair loop
(`MAX_RECOMMENDATION_ATTEMPTS = 3`). Outer runner used `--rec-retries 1`, so there
was no outer redraw after the internal loop failed.

## Final validator error (raised)

```
Major sections deleted in recommended Markdown: ['A useful mental model: delegation as a context firewall', 'Subagents are a form of context architecture', 'Subagents versus MCP', 'Subagents versus skills', 'The architecture after v0.12', 'The journey so far', 'What does the actual demo do?', "What's next?", 'v0.10 — Skills', 'v0.12 — Subagents', 'v0.8 — Memory', 'v0.9 — Compaction']
```

### Deleted headings (12)

1. A useful mental model: delegation as a context firewall
2. Subagents are a form of context architecture
3. Subagents versus MCP
4. Subagents versus skills
5. The architecture after v0.12
6. The journey so far
7. What does the actual demo do?
8. What's next?
9. v0.10 — Skills
10. v0.12 — Subagents
11. v0.8 — Memory
12. v0.9 — Compaction

## Repair loop (what was sent back to Luna)

Per tip code in `aeo_mvp.recommendations.generate_recommendations`:

| Attempt | Prompt | Known outcome |
|---|---|---|
| 1 | Base recommend prompt (CURRENT = original article) | Validation failed (exact intermediate error **not persisted** by runner) |
| 2 | Same base prompt + `REPAIR FEEDBACK` with exact prior validator error | Validation failed again (intermediate error **not persisted**) |
| 3 | Same base prompt + `REPAIR FEEDBACK` (second-repair note) with **latest** validator error only | Failed with the final error above → raised `LLMError` |

`REPAIR FEEDBACK` block shape (from tip):

```
REPAIR FEEDBACK:
The previous recommendation failed deterministic validation.

Validator error:
<exact LLMError text>

[This is a second repair attempt. Fix only the latest failure below.]  # attempt 3 only
Repair this exact failure.
Do not make unrelated changes.
Re-evaluate the opportunity and recommended_markdown together.
...
```

**Guarantees that held:**

- Failed RECOMMENDED was never fed back as CURRENT.
- Transient transport/API errors (if any) would redraw the original prompt without a repair block; this Luna failure is a **validation** failure, so repair feedback was used on attempts 2–3.

**Caveat:** the runner only surfaces the **final** raised `LLMError`. Distinct per-attempt intermediate errors (if they differed) were not written to disk.

## Timings

| Phase | Elapsed |
|---|---|
| Questions | 17.4s (9 questions) |
| Visibility | 174.5s (`retrieval_used=true`) |
| Recommendations (all internal attempts) | ~145.2s then fail |

## Related

- Pack README: [README.md](./README.md)
- Compare (Luna vs Astra): [../live-astra-vs-luna-z2h12-20260923.md](../live-astra-vs-luna-z2h12-20260923.md)
