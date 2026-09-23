# PR #49 paid live — Astra (`openai-gpt-6-astra`) — systematic decision-method tip

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
export AEO_LLM_MODEL=openai-gpt-6-astra
# AEO_LLM_API_KEY, AEO_LLM_BASE_URL, AEO_API_KEY already set on CoS box
python -m aeo_mvp.cli fixtures/agents-z2h-live.md \
  --domain nik-hil.hashnode.dev \
  --live \
  --out docs/live-astra-20260923-063848/
```

## Counts

| Metric | Value |
|--------|-------|
| Questions | 9 |
| Opportunities | 5 |
| CURRENT bytes | 12577 |
| RECOMMENDED bytes | 13820 |
| DIFF bytes | 2279 |
| `llm_used` | True |
| `retrieval_used` | True |
| Visibility mention_rate | 1.0 |
| Visibility citation_rate | 1.0 |
| Visibility target_in_sources_rate | 1.0 |
| Visibility query_coverage | 1.0 |
| Visibility provider | digitalocean_web_search |
| `quality_eval.passed` | False |
| `auto_publish` | False |

## Opportunity targets (multi-section)

1. Feeding the result back to the model
2. The finish tool
3. Why the message history matters
4. There is already a security problem
5. Running the project

Answerability tags: ['weak', 'weak', 'weak', 'missing', 'missing']

## Consistency & spam checks

| Check | Result |
|-------|--------|
| Forward opp → RECOMMENDED body change | **HELD** 5/5 |
| Reverse section change → opportunity | **HELD** |
| Multi-section (not intro-only) | **yes** (5 body sections) |
| Horizontal-rule `---` spam delta | 0 |
| quality_eval unsupported_claims | 2 |

## Quality note

quality_eval **FAIL**. Summary: The questions are realistic, relevant, specific, and sufficiently distinct, and most edits improve technical clarity without disrupting the article. The recommended Markdown better explains tool-result matching, explicit termination, conversation history, and execution security. However, it adds repository-specific OpenRouter setup instructions that are not established by the supplied original or independently supported evidence. Those claims need verification or removal before the draft passes grounding review.

Unsupported (if any):
- “The early versions use OpenRouter's OpenAI-compatible endpoint” is not supported by the original article. The structured changes mention a supplied visibility observation, but no such observation or repository excerpt is included.
- The instruction to set OPENROUTER_API_KEY assumes a repository-specific credential variable that the supplied evidence does not verify.

## Artifacts

`CURRENT.md`, `RECOMMENDED.md`, `DIFF.patch`, `report.json` (includes opportunities + quality_eval), this `README.md`.
