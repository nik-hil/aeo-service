# Live AEO acceptance: Astra vs Luna (2026-09-23 IST)

Paid live runs on Grok Bot box against fixture `fixtures/agents-z2h-live.md` (domain `nik-hil.hashnode.dev`). Tip: `7c8add7328050f5b69356108ad27fd437551491a` (full-document recommendation engine).

| | Astra | Luna |
|---|---|---|
| Model | `openai-gpt-6-astra` | `openai-gpt-5.6-luna` |
| Out dir | `docs/live-astra-20260923-033044/` | `docs/live-luna-20260923-034021/` |
| llm_used / retrieval_used / auto_publish | true / true / false | true / true / false |
| Questions | 8 | 9 |
| Opportunities | 6 | 5 |
| Unique `target_heading`s | 6 | 5 |
| Multi-section (non-intro) edits | yes | yes |
| quality_eval.passed | true | true |
| Unsupported claims (quality_eval) | 2 (metadata only; not in RECOMMENDED) | 0 |
| RECOMMENDED leading/trailing `---` | none | none |
| Direct-answer spam | 0 | 0 |
| First-attempt success | yes | no (validation fail; retry OK) |

Luna first attempt (`docs/live-luna-20260923-033623` not written) raised:

`LLMError: Opportunities target non-intro sections but RECOMMENDED bodies are unchanged for: ['Implementing execute\_code']. Full-document question→section edits required.`

Retry succeeded and is the artifact used below.

## Question quality

Both models produced 5–10 **article-specific** questions (not heading transforms like “What is Repository?”).

**Astra samples**

1. How can I build a minimal AI agent in Python that calls tools without using an agent framework?
2. What does an agent harness do that an LLM alone cannot?
3. How do I turn an LLM tool call into a Python function invocation?
4. How should I send tool results back to an LLM so it can decide what to do next?
5. Why give an AI agent a finish tool instead of treating a normal assistant response as completion?

**Luna samples**

1. How do you build a minimal AI agent that can call Python tools and decide when to stop?
2. What is the difference between an LLM, an AI agent, and an agent harness?
3. How does tool calling connect an LLM's structured response to an actual Python function?
4. Why does an AI agent need to send tool results and previous messages back to the model?
5. Why use an explicit finish tool instead of ending when the model returns a normal assistant response?

Verdict: **tie / slight Astra edge** on operational specificity (security, execute_code output contract, local run). Luna equally natural and distinct.

## Opportunity section distribution

Schema for both: `question` / `gap` / `target_heading` / `recommended_change` / `evidence_quote`. All `target_heading` values matched real article headings; `evidence_quote` values were substrings of CURRENT.

**Astra unique target_headings (6)**

- The agent loop
- Feeding the result back to the model
- The finish tool
- There is already a security problem
- Implementing execute\_code
- Running the project

**Luna unique target_headings (5)**

- The agent loop
- What exactly are we building?
- Handling a tool call
- The finish tool
- Why the message history matters

Neither run concentrated all opportunities on the intro/first section. Astra spread into mid/late sections (security, execute_code, running the project). Luna included one early section (“What exactly are we building?”) plus mid-article tooling/history sections.

## Recommended change quality

- **Astra**: Stronger on protocol precision (tool_call_id / message ordering), security boundaries vs sandboxing, and execute_code return contract. Added a local-setup summary that quality_eval flagged as mildly repetitive (still grounded). Diff ~4.0 KB; RECOMMENDED ~14801 chars.
- **Luna**: Clean conceptual distinctions (LLM vs agent vs harness), dispatch path, finish vs no-tool-call break, history purpose. Smaller, tighter diff (~2.7 KB; RECOMMENDED ~13505 chars). Change explanations also mention a security strengthening even though no dedicated security opportunity row was listed.

Both preserved title/structure; no Direct-answer spam; no leading/trailing YAML `---`.

## Multi-section vs intro-only

**Both multi-section.** Astra: 6/6 targets non-intro. Luna: 4/5 non-intro (one early conceptual section). Full-document question→section behavior confirmed on tip.

## Readability

Luna’s recommended prose is slightly more compact. Astra’s additions are denser/technical but remain readable; quality_eval noted modest repetition only in the setup summary.

## Hallucination / unsupported flags

- **Astra**: quality_eval PASS overall, but flagged 2 unsupported claims in **opportunity metadata** about observed API answers (not present in RECOMMENDED.md). Minor metadata hygiene issue.
- **Luna**: quality_eval PASS with **empty** `unsupported_claims`.

## Reliability note

Luna required a **retry** after failing deterministic full-document validation (opportunity claimed a section edit that RECOMMENDED did not apply). Astra passed on first attempt.

## Default recommendation

**Keep `openai-gpt-6-astra` as default.**

Rationale: broader multi-section coverage on this fixture (security + execution contract + run instructions), first-attempt validation success, and question set aligned with practical AEO gaps. Luna was cleaner on unsupported-claim hygiene and slightly more readable, but not clearly better overall on this run, and one validation failure lowers confidence for unattended paid acceptance.

## Artifacts to commit (no keys)

- `docs/live-astra-20260923-033044/` (`CURRENT.md`, `RECOMMENDED.md`, `DIFF.patch`, `report.json`)
- `docs/live-luna-20260923-034021/` (same)
- `docs/live-astra-vs-luna-20260923.md` (this file)
