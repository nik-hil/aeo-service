# Astra vs Luna — PR #49 paid live acceptance (material recommend prompt)

**Date:** 2026-09-23 (Asia/Calcutta)  
**Tip:** `8632a4c97ecf11d87985b7c5c3b002e73c12f03b` (`cursor/material-aeo-recommend-prompt-2b61`) under `/workspace/pr49-aeo`  
**Fixture:** `fixtures/agents-z2h-live.md` (local MD; Hashnode CF 403 avoided)  
**Domain:** `nik-hil.hashnode.dev`  
**Paid retrieval:** `AEO_PAID_RETRIEVAL_OPT_IN` set  
**auto_publish:** false (both; no Hashnode publish)

| | Astra | Luna |
|---|---|---|
| Out dir | `docs/live-astra-20260923-052632/` | `docs/live-luna-20260923-053240/` |
| Model | `openai-gpt-6-astra` | `openai-gpt-5.6-luna` |
| `llm_used` | true | true |
| `retrieval_used` | true | true |
| `auto_publish` | false | false |
| Questions | 9 | 8 |
| Opportunities | **2** | **2** |
| CURRENT bytes | 12577 | 12577 |
| RECOMMENDED bytes | 13178 | 12919 |
| DIFF bytes | 983 | 767 |
| Visibility mention_rate | 1.0 | 1.0 |
| Visibility citation_rate | 1.0 | 1.0 |
| Visibility target_in_sources_rate | 1.0 | 1.0 |
| Visibility query_coverage | 1.0 | 1.0 |
| Visibility provider | digitalocean_web_search | digitalocean_web_search |
| `quality_eval.passed` | true | true |

## Consistency invariants

Checked programmatically against CURRENT.md / RECOMMENDED.md / opportunities (same forward+reverse contract the pipeline enforces):

| Invariant | Astra | Luna |
|---|---|---|
| **Forward:** every opportunity `target_heading` body differs CURRENT vs RECOMMENDED | **HELD** (2/2) | **HELD** (2/2) |
| **Reverse:** every substantive section change has an opportunity | **HELD** | **HELD** |
| Multi-section (not intro-only) | yes (2 body sections) | yes (2 body sections) |
| No horizontal rule `---` lines | yes (0) | yes (0) |
| No Direct-answer spam | yes (0) | yes (0) |
| `quality_eval` pass | yes | yes |
| `auto_publish` false | yes | yes |

### Astra opportunity targets
Feeding the result back to the model; There is already a security problem.

### Luna opportunity targets
Feeding the result back to the model; Why the message history matters.

## Material usefulness (vs PR #48 restatement style)

PR #48 paid live on the same fixture produced **7 opportunities** per model with broader, often expansive section edits. PR #49’s rewritten 8-pass material-recommend prompt yields **2 opportunities** each — both tagged `answerability: weak` and both adding net-new clarifying sentences rather than restating already-strong sections.

**Shared material gap both models found**
- `tool_call_id` binding when feeding tool results back (both edited “Feeding the result back to the model”).

**Astra-only material gap**
- Security: subprocess/timeout ≠ sandbox; harness pre-dispatch checks vs execution-environment constraints (“There is already a security problem”).

**Luna-only material gap**
- Message-history contract: preserve the assistant tool-call message, then append the matching tool result (“Why the message history matters”).

Neither run used the intro/H1 as the edit target. Neither invented citations/stats. Diffs are small, multi-section, and opportunity↔diff consistent.

Astra `quality_eval` noted a remaining implementation gap (snippets still don’t show appending the assistant tool-call message before tool results) and a minor transition wording issue after the security insert — neither failed the pass. Luna’s two edits are leaner; it did not surface the security sandbox clarification Astra did.

## Default-model recommendation

**Keep `openai-gpt-6-astra` as the default.**

Rationale: Luna is not clearly better. Both pass consistency + quality_eval; visibility ties; both are multi-section and non-restatement. Astra’s security clarification is a higher-value material gap for this fixture; Luna’s history-preservation note is also material but overlaps more with content already nearby. Prefer Astra unless a future fixture shows Luna systematically better on answerability without restatement.

## Artifacts

- Astra: `docs/live-astra-20260923-052632/{CURRENT.md,RECOMMENDED.md,DIFF.patch,report.json,README.md}`
- Luna: `docs/live-luna-20260923-053240/{CURRENT.md,RECOMMENDED.md,DIFF.patch,report.json,README.md}`
- This compare: `docs/live-astra-vs-luna-20260923.md`
- Pack: `/workspace/pr49-live-material-20260923.tar.gz`

## Non-actions (explicit)

- Did **not** merge PR #49
- Did **not** Hashnode-publish
- Did **not** push (gh unauthed on this box; CoS cloud-agent will push)
- Did **not** log or commit API keys
