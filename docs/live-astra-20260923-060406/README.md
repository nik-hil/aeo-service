# PR #49 paid live — Astra (`openai-gpt-6-astra`) — materiality rebalance tip

**When:** 2026-09-23 ~11:34–11:40 IST (Asia/Calcutta)  
**Tip under test:** `9f03896513c435e8372b1955ea60ca3596229b79` (`cursor/material-aeo-recommend-prompt-2b61`)  
**Checkout:** `/workspace/pr49-aeo`  
**auto_publish:** false (pipeline hard-codes; no Hashnode publish)

## Fixture source

Local Markdown preferred (Hashnode live fetch blocked by Cloudflare 403):

- Path: `fixtures/agents-z2h-live.md`
- Meta: `fixtures/agents-z2h-live.meta.json`
- Original URI: `https://nik-hil.hashnode.dev/agents-zero-to-hero-1-building-an-ai-agent-from-scratch-with-tool-calling.md`
- Domain: `nik-hil.hashnode.dev`

## Invocation

```bash
export AEO_LLM_MODEL=openai-gpt-6-astra
# AEO_LLM_API_KEY, AEO_LLM_BASE_URL, AEO_API_KEY, AEO_PAID_RETRIEVAL_OPT_IN already set
python -m aeo_mvp.cli fixtures/agents-z2h-live.md \
  --domain nik-hil.hashnode.dev \
  --live \
  --out docs/live-astra-20260923-060406/
```

## Counts

| Metric | Value |
|--------|-------|
| Questions | 8 |
| Opportunities | 4 |
| CURRENT bytes | 12577 |
| RECOMMENDED bytes | 13541 |
| DIFF bytes | 1711 |
| `llm_used` | true |
| `retrieval_used` | true |
| Visibility mention_rate | 1.0 |
| Visibility citation_rate | 1.0 |
| Visibility target_in_sources_rate | 1.0 |
| Visibility query_coverage | 1.0 |
| Visibility provider | digitalocean_web_search |
| `quality_eval.passed` | true |
| `auto_publish` | false |

## Opportunity targets (multi-section)

1. Feeding the result back to the model
2. The finish tool
3. Why the message history matters
4. There is already a security problem

Answerability tags: ['weak', 'weak', 'weak', 'weak']

## Consistency & spam checks

| Check | Result |
|-------|--------|
| Forward opp → RECOMMENDED body change | **HELD** 4/4 |
| Reverse section change → opportunity | **HELD** |
| Multi-section (not intro-only) | **yes** (4 body sections) |
| Horizontal-rule `---` spam | 0 |
| Direct-answer templates | 0 |
| Pure restatement opportunities | 0 (gaps tagged weak; net-new clarifying sentences) |

## Vs prior PR49 over-conservative run (tip `8632a4c`, 2 opps)

This tip (`9f03896`) keeps partial-answer gaps: **4** opportunities vs prior **2**, still well below PR48-style ~7 restatement volume. New vs prior: finish-tool loop-termination clarification + message-history completeness; retained tool_call_id + security sandbox vs timeout distinctions.

## Artifacts

`CURRENT.md`, `RECOMMENDED.md`, `DIFF.patch`, `report.json` (includes opportunities + quality_eval), this `README.md`.
