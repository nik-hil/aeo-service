# PR #49 paid live — Astra (`openai-gpt-6-astra`)

**When:** 2026-09-23 ~05:26–05:32 IST (Asia/Calcutta)  
**Tip under test:** `8632a4c97ecf11d87985b7c5c3b002e73c12f03b` (`cursor/material-aeo-recommend-prompt-2b61`)  
**Checkout:** `/workspace/pr49-aeo`  
**auto_publish:** false (pipeline hard-codes; no Hashnode publish)

## Fixture source

Local Markdown preferred (Hashnode live fetch blocked by Cloudflare 403):

- Path: `fixtures/agents-z2h-live.md` (copied from `/workspace/pr48-aeo/fixtures/agents-z2h-live.md`)
- Meta: `fixtures/agents-z2h-live.meta.json`
- Original URI: `https://nik-hil.hashnode.dev/agents-zero-to-hero-1-building-an-ai-agent-from-scratch-with-tool-calling.md`
- Crawl note: Safari-on-Mac capture; automated curl/GQL failed CF/Pro
- Domain: `nik-hil.hashnode.dev`

## Invocation

```bash
export AEO_LLM_MODEL=openai-gpt-6-astra
# AEO_LLM_API_KEY, AEO_LLM_BASE_URL, AEO_API_KEY, AEO_PAID_RETRIEVAL_OPT_IN already set
python -m aeo_mvp.cli fixtures/agents-z2h-live.md \
  --domain nik-hil.hashnode.dev \
  --live \
  --out docs/live-astra-20260923-052632/
```

## Counts

| Metric | Value |
|--------|-------|
| Questions | 9 |
| Opportunities | 2 |
| CURRENT bytes | 12577 |
| RECOMMENDED bytes | 13178 |
| DIFF bytes | 983 |
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
2. There is already a security problem

Answerability tags: ['weak', 'weak']

## Consistency & spam checks

| Check | Result |
|-------|--------|
| Forward opp → RECOMMENDED body change | **HELD** 2/2 |
| Reverse section change → opportunity | **HELD** |
| Multi-section (not intro-only) | **yes** (2 body sections) |
| Horizontal-rule `---` spam | 0 |
| Direct-answer templates | 0 |
| Pure restatement opportunities | 0 (gaps tagged weak; net-new clarifying sentences) |

## Artifacts

`CURRENT.md`, `RECOMMENDED.md`, `DIFF.patch`, `report.json` (includes opportunities + quality_eval), this `README.md`.
