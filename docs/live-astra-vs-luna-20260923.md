# PR #49 CoS paid live — Astra vs Luna (diagnosis-vs-content tip)

**Date:** 2026-09-23 IST (Asia/Calcutta)  
**Tip:** `992d7bb5d01bc8e30bd7e07391c7008537d85be9` on `cursor/material-aeo-recommend-prompt-2b61`  
**Prompt under test:** diagnosis vs content boundary (*Search evidence tells you WHAT may be weak. CURRENT.md tells you WHAT you are allowed to say.*)  
**Fixture:** `fixtures/agents-z2h-live.md` (local MD; not live HTML)  
**Domain:** `nik-hil.hashnode.dev`  
**Flags:** `--live`, `auto_publish=false`, paid retrieval opt-in fail-closed (env present)

| | Astra (`openai-gpt-6-astra`) | Luna (`openai-gpt-5.6-luna`) |
|--|------:|-----:|
| Output dir | `docs/live-astra-20260923-070422/` | `docs/live-luna-20260923-071044/` |
| Questions | 9 | 9 |
| Opportunities | 3 | 1 |
| Opp↔RECOMMENDED consistency | held | held |
| Multi-section | **yes** (3 targets) | **no** (1 target) |
| `quality_eval.passed` | **True** | **True** |
| Unsupported claims | [] | [] |
| Search-imported facts (OpenRouter / API keys / providers) | **none** | **none** |
| `llm_used` / `retrieval_used` | True / True | True / True |

## Qualitative grounding

### Astra
- **Edits:** (1) `tool_call_id` association at “Feeding the result back…”, (2) finish vs no-tool-call loop at “The finish tool”, (3) assistant tool-call + result retention at “Why the message history matters”.
- **Grounding:** All three statements are authorized by CURRENT (code field, finish section, history diagram). Diagnosis from search/questions → content from CURRENT.
- **Vs prior systematic tip (`e5523b9`):** Astra previously *failed* quality_eval by injecting OpenRouter / `OPENROUTER_API_KEY`. This tip clears that failure mode.
- **Editing volume:** Mid-band, multi-section clarifications; not over-edited. Cosmetic no-op trailing line only.

### Luna
- **Edits:** One paragraph in “Why the message history matters” covering history + `tool_call_id`.
- **Grounding:** Clean CURRENT-grounded clarification; no search imports.
- **Editing volume:** Under-edits — skips finish-tool clarity gap that CURRENT already supports. Not multi-section.

## Recommendation

**Keep Astra as default** (`AEO_LLM_MODEL=openai-gpt-6-astra`).

Rationale (grounding quality, not opp count alone): On this diagnosis-vs-content tip Astra finally passes quality_eval with zero unsupported / search-imported claims while still producing multi-section CURRENT-grounded clarifications. Luna is also grounded but under-edits (1 section). Prefer Astra for answerability coverage without the prior over-reach.

Luna remains the concise compare model via `AEO_LLM_MODEL=openai-gpt-5.6-luna`.

## Blockers

None for this acceptance pack. Do not push/merge from CoS; use push-instructions file.

