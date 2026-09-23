# PR #49 paid live — Luna (`openai-gpt-5.6-luna`) — systematic decision-method tip

**When:** 2026-09-23 IST (Asia/Calcutta)  
**Tip under test:** `e5523b92716ed0d0c903308b2b108137b778df92` (`cursor/material-aeo-recommend-prompt-2b61`)  
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
export AEO_LLM_MODEL=openai-gpt-5.6-luna
# AEO_LLM_API_KEY, AEO_LLM_BASE_URL, AEO_API_KEY already set on CoS box
python -m aeo_mvp.cli fixtures/agents-z2h-live.md \
  --domain nik-hil.hashnode.dev \
  --live \
  --out docs/live-luna-20260923-064555/
```

## Counts

| Metric | Value |
|--------|-------|
| Questions | 9 |
| Opportunities | 3 |
| CURRENT bytes | 12577 |
| RECOMMENDED bytes | 13865 |
| DIFF bytes | 2025 |
| `llm_used` | True |
| `retrieval_used` | True |
| Visibility mention_rate | 1.0 |
| Visibility citation_rate | 1.0 |
| Visibility target_in_sources_rate | 1.0 |
| Visibility query_coverage | 1.0 |
| Visibility provider | digitalocean_web_search |
| `quality_eval.passed` | True |
| `auto_publish` | False |

## Opportunity targets (multi-section)

1. The finish tool
2. Why the message history matters
3. There is already a security problem

Answerability tags: ['strong', 'strong', 'strong']

## Consistency & spam checks

| Check | Result |
|-------|--------|
| Forward opp → RECOMMENDED body change | **HELD** 3/3 |
| Reverse section change → opportunity | **HELD** |
| Multi-section (not intro-only) | **yes** (3 body sections) |
| Horizontal-rule `---` spam delta | 0 |
| quality_eval unsupported_claims | 0 |

## Quality note

quality_eval **PASS**. Summary: The questions are realistic, relevant, distinct, and specific to the article, and the recommended Markdown improves answerability with targeted clarifications rather than broad rewrites. The additions explain the value of an explicit finish signal, preserve tool-call/result associations in message history, and make the execution-security implications and safeguard location clearer. The recommendations remain grounded in the article and introduce no material unsupported facts, statistics, or citations.

Unsupported (if any):
(none)

## Artifacts

`CURRENT.md`, `RECOMMENDED.md`, `DIFF.patch`, `report.json` (includes opportunities + quality_eval), this `README.md`.
