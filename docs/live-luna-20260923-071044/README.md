# PR #49 paid live — Luna (`openai-gpt-5.6-luna`) — diagnosis-vs-content tip

**When:** 2026-09-23 IST (Asia/Calcutta)  
**Tip under test:** `992d7bb5d01bc8e30bd7e07391c7008537d85be9` (`cursor/material-aeo-recommend-prompt-2b61`)  
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
python -m aeo_mvp.cli fixtures/agents-z2h-live.md \
  --domain nik-hil.hashnode.dev \
  --live \
  --out docs/live-luna-20260923-071044/
```

## Counts

| Metric | Value |
|--------|-------|
| Questions | 9 |
| Opportunities | 1 |
| CURRENT bytes | 12577 |
| RECOMMENDED bytes | 12862 |
| DIFF bytes | 605 |
| `llm_used` | True |
| `retrieval_used` | True |
| Visibility mention_rate | 1.0 |
| Visibility citation_rate | 1.0 |
| Visibility target_in_sources_rate | 1.0 |
| Visibility query_coverage | 1.0 |
| Visibility provider | digitalocean_web_search |
| `quality_eval.passed` | True |
| `auto_publish` | False |

## Opportunity targets

1. Why the message history matters

Answerability tags: ['weak']

## Consistency & spam checks

| Check | Result |
|-------|--------|
| Opp↔RECOMMENDED bidirectional (`validation_warnings`) | held (empty) |
| Multi-section (not intro-only) | no (single section) |
| OpenRouter / OPENROUTER_API_KEY / external provider setup | none |
| `quality_eval.unsupported_claims` | [] |

## Grounding lens (diagnosis vs content)

Single CURRENT-grounded clarification combining history preservation + tool_call_id association. No search-imported facts. Under-edits relative to Astra (misses finish-tool and dedicated tool_call_id placement clarifications).

## Note

DIFF shows a no-op trailing line rewrite of "One Git tag at a time." (cosmetic; no content change).
