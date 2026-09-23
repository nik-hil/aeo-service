# Astra vs Luna — PR #48 paid live acceptance

**Date:** 2026-09-23 (Asia/Calcutta)  
**Tip:** `baf4e6d` (`/workspace/pr48-aeo`)  
**Fixture:** `fixtures/agents-z2h-live.md`  
**Domain:** `nik-hil.hashnode.dev`  
**Base URL:** `https://inference.do-ai.run/v1`  
**Paid retrieval:** `AEO_PAID_RETRIEVAL_OPT_IN=1`  
**auto_publish:** false (both; no Hashnode publish)

| | Astra | Luna |
|---|---|---|
| Out dir | `docs/live-astra-20260923-040706/` | `docs/live-luna-20260923-045101/` |
| Model | `openai-gpt-6-astra` | `openai-gpt-5.6-luna` |
| `llm_used` | true | true |
| `retrieval_used` | true | true |
| `auto_publish` | false | false |
| Questions | 9 | 8 |
| Opportunities | 7 | 7 |
| Recommended chars | 14014 | 13558 |
| CURRENT bytes | 12577 | 12577 |
| RECOMMENDED bytes | 14496 | 14040 |
| Visibility mention_rate | 1.0 | 1.0 |
| Visibility citation_rate | 1.0 | 1.0 |
| Visibility target_in_sources_rate | 1.0 | 1.0 |
| Visibility query_coverage | 1.0 | 1.0 |
| Visibility provider | digitalocean_web_search | digitalocean_web_search |
| `quality_eval.passed` | true | true |

## Consistency invariants

Checked programmatically against CURRENT.md / RECOMMENDED.md / opportunities:

| Invariant | Astra | Luna |
|---|---|---|
| **Forward:** every opportunity `target_heading` body differs CURRENT vs RECOMMENDED | **HELD** (7/7) | **HELD** (7/7) |
| **Reverse:** every substantive section change has an opportunity | **HELD** (7/7) | **HELD** (7/7) |
| Multi-section (not intro-only) | yes (7 distinct body sections) | yes (7 distinct body sections) |
| No horizontal rule `---` lines | yes | yes |
| No Direct-answer spam | yes (0 matches) | yes (0 matches) |
| `quality_eval` pass | yes | yes |
| `auto_publish` false | yes | yes |

### Astra opportunity targets
Implementing execute\_code; The finish tool; Calling the model; Feeding the result back to the model; Why the message history matters; There is already a security problem; Running the project.

### Luna opportunity targets
The agent loop; The complete flow; Tool schemas; Feeding the result back to the model; The finish tool; There is already a security problem; Why the message history matters.

## Qualitative comparison

**Shared strengths.** Both runs produce grounded, multi-section edits that clarify harness vs model, tool-result feedback, finish signaling, message history, and security. Neither invents citations/stats; both preserve structure and code blocks. Paid retrieval visibility is saturated (1.0) for both on this domain/fixture.

**Astra edges.**
- Broader question set (9 vs 8), including `tool_choice="auto"` and a more concrete execute_code/timeout question.
- Edits tend to be more operational: timeout/output fields, `tool_call_id` matching, preserve-assistant-tool-call guidance, naming `v0.1-basic-tool` in Running the project.
- `quality_eval.unnecessary_changes` empty.

**Luna edges / gaps.**
- Cleaner conceptual framing of agent-loop / schema-as-contract / LLM-as-decision-maker (good teaching prose).
- Slightly leaner RECOMMENDED (+~1.5k vs Astra +~1.9k chars).
- Quality eval flagged minor security-section repetition and some sentences that could be shorter.
- Dropped the `tool_choice="auto"` and execute_code/timeout angles that Astra covered.

**Astra quality note.** One opportunity justification mentioned an "observed API answer failed to recover" without evidence in the report; quality_eval flagged that as unsupported *justification* only — recommended Markdown itself was not blamed. Does not break the pass.

## Default recommendation

**Keep `openai-gpt-6-astra` as the default model.**

Rationale: Luna is not clearly better. Consistency and quality pass on both; visibility ties. Astra’s question coverage and opportunity specificity (timeouts, tool_choice, run instructions) are slightly stronger for this fixture, and Luna’s quality notes call out avoidable repetition. Switch only if a future fixture shows Luna systematically better on answerability without repetition.

## Artifacts

- Astra: `docs/live-astra-20260923-040706/{CURRENT,RECOMMENDED,DIFF.patch,report.json}`
- Luna: `docs/live-luna-20260923-045101/{CURRENT,RECOMMENDED,DIFF.patch,report.json}`
- This compare: `docs/live-astra-vs-luna-20260923.md`
- Pack: `/workspace/pr48-live-consistency-20260923.tar.gz`

## Non-actions (explicit)

- Did **not** merge PR #48
- Did **not** Hashnode-publish
- Did **not** push (gh unauthed; CoS cloud-agent will push)
- Did **not** log or commit API keys
