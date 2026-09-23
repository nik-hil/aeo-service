# Live Astra + DigitalOcean web_search acceptance (PR #50)

- **Branch:** `cursor/exact-page-visibility-3ea9`
- **Tip SHA:** `8e98531b2bb020e4573edae98557e9f454c47546`
- **Model:** `openai-gpt-6-astra`
- **Provider (visibility):** `digitalocean_web_search`
- **URI / fixture:** `fixtures/agents-z2h12-live.md`
- **target_url:** `https://nik-hil.hashnode.dev/agents-zero-to-hero-12-building-ai-subagents-with-context-isolation`
- **target_domain:** `nik-hil.hashnode.dev`
- **Flags:** `--live`, `AEO_PAID_RETRIEVAL_OPT_IN=1`, `AEO_LIVE_RETRIEVAL_TEST=true`
- **Out dir:** `docs/live-astra-20260923-114943`
- **Exit code:** `0` (success)

## Usage flags

| Flag | Value |
| --- | --- |
| retrieval_used | true |
| llm_used | true |

## Visibility rates

| Metric | Value |
| --- | --- |
| mention_rate | 1.0 |
| citation_rate | 1.0 |
| target_in_sources_rate (domain) | 1.0 |
| target_page_in_sources_rate | 0.0 |
| target_page_citation_rate | 0.0 |

## Observation counts (n=10)

| Condition | Count |
| --- | --- |
| target_domain_in_sources=true | 10 |
| target_page_in_sources=true | 0 |
| target_page_in_sources=false | 10 |
| domain=true AND page=false | 10 |

## Example: domain=true, page=false

Occurred on **all 10** observations. Concrete example:

- **query:** How do subagents reduce context overload in an AI coding agent, and how is that different from context compaction?
- **target_domain_in_sources:** true
- **target_page_in_sources:** false
- **target_page_cited:** false
- **cited / mentioned:** true / true
- **source_urls (sample):**
  - https://nik-hil.hashnode.dev/agents-zero-to-hero-1-building-an-ai-agent-from-scratch-with-tool-calling
  - https://nik-hil.hashnode.dev/agents-zero-to-hero-6-teaching-an-ai-agent-when-it-is-allowed-to-act
  - https://nik-hil.hashnode.dev/agents-zero-to-hero-2-giving-an-ai-agent-eyes-and-hands-filesystem-tools

Exact target page URL did not appear in sources; other pages on the same Hashnode domain did.

## Opportunities / quality_eval

- **opportunity count:** 1
- **quality_eval.passed:** true

## Artifacts

- `CURRENT.md`, `RECOMMENDED.md`, `DIFF.patch`, `report.json`, `run.log`, `SUMMARY.md`

No secrets included.
