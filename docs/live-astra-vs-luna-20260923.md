# PR #49 CoS paid live — Astra vs Luna (systematic decision-method)

**Date:** 2026-09-23 IST (Asia/Calcutta)  
**Tip:** `e5523b92716ed0d0c903308b2b108137b778df92` on `cursor/material-aeo-recommend-prompt-2b61`  
**Fixture:** `fixtures/agents-z2h-live.md` (local MD; Cloudflare blocks live HTML)  
**Domain:** `nik-hil.hashnode.dev`  
**auto_publish:** false  

## Scoreboard

| Metric | Astra (`openai-gpt-6-astra`) | Luna (`openai-gpt-5.6-luna`) |
|--------|------------------------------|------------------------------|
| Output dir | `docs/live-astra-20260923-063848` | `docs/live-luna-20260923-064555` |
| Questions | 9 | 9 |
| Opportunities | 5 | 3 |
| Opp ↔ RECOMMENDED forward | HELD 5/5 | HELD 3/3 |
| Reverse section → opp | HELD | HELD |
| Multi-section (not intro-only) | yes (5) | yes (3) |
| quality_eval | FAIL | PASS |
| unsupported_claims | 2 | 0 |
| llm_used / retrieval_used | True / True | True / True |
| DIFF bytes | 2279 | 2025 |

## Opportunity targets

**Astra:** Feeding the result back to the model, The finish tool, Why the message history matters, There is already a security problem, Running the project  
**Luna:** The finish tool, Why the message history matters, There is already a security problem

## Qualitative

- **Astra:** over-reached with unsupported/repository-specific claims; mid-band opportunity count (target ~3–5); quality gate failed. quality_eval summary: The questions are realistic, relevant, specific, and sufficiently distinct, and most edits improve technical clarity without disrupting the article. The recommended Markdown better explains tool-result matching, explicit termination, conversation history, and execution security. However, it adds repository-specific OpenRouter setup instructions that are not established by the supplied original or independently supported evidence. Those claims nee
- **Luna:** mid-band opportunity count (target ~3–5); genuine clarifications grounded in article. quality_eval summary: The questions are realistic, relevant, distinct, and specific to the article, and the recommended Markdown improves answerability with targeted clarifications rather than broad rewrites. The additions explain the value of an explicit finish signal, preserve tool-call/result associations in message history, and make the execution-security implications and safeguard location clearer. The recommendations remain grounded in the article and introduce 

## Materiality band

Target behavior: each question gets exactly enough editing then stops (between PR #48 shallow ~7 and early PR #49 over-conservative ~2).

- Astra opportunities: **5**
- Luna opportunities: **3**

## Recommendation

**Keep Luna as default** for this tip.

Luna passed quality_eval with zero unsupported claims and mid-band, multi-section clarifications (finish signal, history/tool_call_id association, security boundary). Astra produced more opportunities (incl. Running the project) but failed quality_eval by injecting unverified OpenRouter / OPENROUTER_API_KEY setup — classic over-reach. Prefer Luna as default for this systematic-decision-method tip; revisit Astra after tightening grounding for provider/setup claims.

Update `docs/MODELS.md` / config default accordingly only after this pack is committed on the PR.
