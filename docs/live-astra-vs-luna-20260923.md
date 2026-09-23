# Live AEO acceptance: Astra vs Luna (PR #47)

**Date:** 2026-09-23 (Asia/Calcutta)  
**Tip SHA:** `ee076e1bb404b3a77b50e3df00bdc7053959c636` (`cursor/hashnode-aeo-poc-2a89`)  
**Fixture:** `fixtures/agents-z2h-live.md` (Safari-fetched)  
**Domain:** `nik-hil.hashnode.dev`  
**Base URL:** `https://inference.do-ai.run/v1`  
**Mode:** paid live (`--live`); `auto_publish=false` (no Hashnode publish)

| Run | Model | Out dir |
|-----|-------|---------|
| A | `openai-gpt-6-astra` | `docs/live-astra-20260923-023911/` |
| B | `openai-gpt-5.6-luna` | `docs/live-luna-20260923-024514/` |

Also catalog-confirmed: `openai-gpt-6-luna` exists; this acceptance used the PR-documented Luna default (`openai-gpt-5.6-luna`).

## Gate checklist (both runs)

| Check | Astra | Luna |
|-------|-------|------|
| `llm_used` | true | true |
| `retrieval_used` | true | true |
| Question count (5–10) | 9 | 8 |
| Heading-template questions ("What is Repository?") | none | none |
| Duplicated Direct-answer blocks in RECOMMENDED.md | none | none |
| Quality eval present + passed | yes / **pass** | yes / **pass** |
| `auto_publish` | false | false |
| Mention / citation / coverage rates | 1.0 / 1.0 / 1.0 | 1.0 / 1.0 / 1.0 |

## Sample questions

### Astra (`openai-gpt-6-astra`)
1. How can I build a basic AI agent in Python that calls tools without using an agent framework?
2. What makes an LLM with tool calling an agent rather than just a chatbot?
3. How do I turn an LLM tool call into a Python function call and send the result back to the model?
4. How should I maintain conversation history so an AI agent can use tool results and retry failed code?
5. Is running AI-generated Python in a subprocess safe, and where should an agent enforce security controls?

### Luna (`openai-gpt-5.6-luna`)
1. How do I build a minimal AI agent that can call a Python tool, observe the result, and decide when to stop?
2. What is the role of tool schemas, and how does an LLM tool call become an actual Python function invocation?
3. Why use an explicit finish tool instead of treating a normal assistant response as the end of an agent task?
4. What responsibilities belong in an AI agent harness instead of in the language model?
5. What are the security risks of letting an AI agent execute arbitrary Python code?

Neither set is heading→question transforms; both are reader/intent style.

## Comparison

### Question quality / diversity
Both strong and distinct across architecture, schemas/dispatch, history, finish, execution, security, and local run. Astra kept 9/9 candidates; Luna selected 8/9 (dropped a controlled-workspace question as future v0.2). Slight edge: **Astra** (broader coverage without awkward overlap).

### Grounding
Both keep code/structure and avoid inventing provider settings. Astra evaluator flagged unverifiable “observed API answer …” claims in **opportunity rationales** (not in article body). Luna flags were milder (architectural implication + an original-article subjective phrase). Edge: **Luna** on editorial grounding hygiene.

### Opportunity quality
- Astra: **9 structured opportunities** with `target_heading`, problem, recommended_change, answerability; all targets match real section headings.
- Luna: **0 structured opportunities** in `report.json` (recommendations still applied via full MD rewrite + 6 change_explanations). This is a pipeline-output gap for Luna on this run.

Edge: **Astra** (clearly).

### Target-section correctness
Astra targets all valid (`The agent loop`, `Tool schemas`, `The finish tool`, `Running the project`, …). Luna change explanations are coherent but lack machine-checkable targets. Edge: **Astra**.

### Recommended-change quality
Both RECOMMENDED.md files are coherent prose edits (no Direct-answer spam). Astra adds more operational detail (message ordering, `tool_call_id`, finish vs harness stop, non-sandbox subprocess). Luna is tighter and often clearer, but introduced stray leading/trailing `---` lines (frontmatter-like pollution). Edge: **Astra** for substance; Luna for brevity (with a packaging nit).

### Readability
Luna slightly more readable / less repetitive. Astra quality eval noted modest repetition in setup and agent-vs-reply. Edge: **Luna**.

### Hallucination / unsupported-claim flags
Both `quality_eval.passed=true`. Astra: unsupported claims about API-observation evidence in rationales. Luna: mild implication + inherited subjective phrase. Edge: **Luna**.

## Default model recommendation

**Recommend `openai-gpt-6-astra` as the default for this PoC tip**, overriding the prior Luna expectation for this acceptance.

Rationale: on the same fixture/domain, Astra produced complete structured opportunities with correct target headings and more precise recommended changes, while Luna returned an empty opportunities array and polluted RECOMMENDED.md with `---` markers despite a clean quality pass. Luna remains a strong concise alternative and wins on grounding hygiene / readability, but Astra is clearly better on the end-to-end AEO artifact the product needs.

If product preference stays “smaller default model,” keep documenting `openai-gpt-5.6-luna` but gate releases on Astra comparison or fix Luna’s empty-opportunities path first.

## Artifacts

- `docs/live-astra-20260923-023911/{CURRENT,RECOMMENDED,DIFF.patch,report.json}`
- `docs/live-luna-20260923-024514/{CURRENT,RECOMMENDED,DIFF.patch,report.json}`
- This file: `docs/live-astra-vs-luna-20260923.md`

## Notes for retry / CoS

- Box had no `.git`; tip synced via public GitHub tarball of `ee076e1`.
- `gh` not authenticated on box → push may need cursor-github / cloud agent.
- pytest on box: **21 passed, 1 skipped, 2 failed** solely because live env vars are set (`AEO_LLM_MODEL` / key present); mocks otherwise green.
- Sequential paid runs only; Astra ~5.8 min, Luna ~3.5 min wall time.
- Do **not** merge PR #47; do **not** publish to Hashnode from these artifacts.
