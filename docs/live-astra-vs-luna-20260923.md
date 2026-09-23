# Astra vs Luna — PR #49 paid live (materiality rebalance tip `9f03896`)

**Date:** 2026-09-23 (Asia/Calcutta)  
**Tip:** `9f03896513c435e8372b1955ea60ca3596229b79` (`cursor/material-aeo-recommend-prompt-2b61`) under `/workspace/pr49-aeo`  
**Fixture:** `fixtures/agents-z2h-live.md` (local MD; Hashnode CF 403 avoided)  
**Domain:** `nik-hil.hashnode.dev`  
**Paid retrieval:** `AEO_PAID_RETRIEVAL_OPT_IN` set  
**auto_publish:** false (both; no Hashnode publish)

| | Astra | Luna |
|---|---|---|
| Out dir | `docs/live-astra-20260923-060406/` | `docs/live-luna-20260923-061008/` |
| Model | `openai-gpt-6-astra` | `openai-gpt-5.6-luna` |
| `llm_used` | true | true |
| `retrieval_used` | true | true |
| `auto_publish` | false | false |
| Questions | 8 | 8 |
| Opportunities | **4** | **3** |
| CURRENT bytes | 12577 | 12577 |
| RECOMMENDED bytes | 13541 | 13518 |
| DIFF bytes | 1711 | 1654 |
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
| **Forward:** every opportunity `target_heading` body differs CURRENT vs RECOMMENDED | **HELD** (4/4) | **HELD** (3/3) |
| **Reverse:** every substantive section change has an opportunity | **HELD** | **HELD** |
| Multi-section (not intro-only) | yes (4 body sections) | yes (3 body sections) |
| No horizontal rule `---` lines | yes (0) | yes (0) |
| No Direct-answer spam | yes (0) | yes (0) |
| `quality_eval` pass | yes | yes |
| `auto_publish` false | yes | yes |

### Astra opportunity targets
Feeding the result back to the model; The finish tool; Why the message history matters; There is already a security problem.

### Luna opportunity targets
What exactly are we building?; Why the message history matters; There is already a security problem.

## Vs prior PR49 (~2 opp) and PR48 (~7 opp)

| Run | Tip / prompt | Opps (Astra / Luna) | Character |
|---|---|---|---|
| PR #48 | pre-material prompt | ~7 / ~7 | Broad restatement / expansive section rewrites |
| PR #49 prior live | `8632a4c` material prompt (over-conservative) | **2 / 2** | Genuine weak gaps only; missed some partial-answer clarifications |
| PR #49 this live | `9f03896` rebalance (keep partial gaps, stop after sufficiency) | **4 / 3** | More partial-answer clarifications than `8632a4c`, still far below PR48 restatement volume |

Rebalance goal held: not stuck at over-conservative 2 when genuine partial gaps exist; not regressing to PR48-style restatement volume.

## Material usefulness (relationships / clarifications vs restatement)

All opportunities tagged `answerability: weak`. Edits add net-new clarifying sentences (relationships, contracts, distinctions) rather than restating already-strong prose. No invented citations/stats. Diffs remain small and multi-section.

**Shared material gaps (both models)**
- Message-history contract: next request only sees appended messages (“Why the message history matters”).
- Security: harness must enforce controls; timeout/subprocess ≠ sandbox (“There is already a security problem”).

**Astra-only material gaps**
- `tool_call_id` binding when feeding results back (“Feeding the result back to the model”).
- Finish tool returns data vs loop actually terminating (“The finish tool”).

**Luna-only material gap**
- Explicit AI-agent = LLM + tools + harness + state + loop vs harness-as-layer (“What exactly are we building?”) — useful definitional clarify, slightly closer to early-article restatement risk than Astra’s finish/`tool_call_id` gaps.

Neither run used H1/intro-only as the sole edit target. Forward↔reverse opportunity↔RECOMMENDED consistency held on both.

## Default-model recommendation

**Keep `openai-gpt-6-astra` as the default.**

Rationale: Luna is not clearly better. Both pass consistency + quality_eval; visibility ties; both multi-section and non-restatement. Astra surfaces **more** partial-answer material gaps (4 vs 3), including the finish-tool termination distinction and `tool_call_id` binding that Luna missed this run. Luna’s agent-vs-harness definitional note is fine but not enough to displace Astra. Prefer Astra unless a future fixture shows Luna systematically better on answerability without restatement.

## Artifacts

- Astra: `docs/live-astra-20260923-060406/{CURRENT.md,RECOMMENDED.md,DIFF.patch,report.json,README.md}`
- Luna: `docs/live-luna-20260923-061008/{CURRENT.md,RECOMMENDED.md,DIFF.patch,report.json,README.md}`
- This compare: `docs/live-astra-vs-luna-20260923.md`
- Pack: `/workspace/pr49-live-material-rebalance-20260923.tar.gz`

## Non-actions (explicit)

- No Hashnode publish (`auto_publish` false).
- No merge of PR #49.
- No secrets in artifacts or tarball.
