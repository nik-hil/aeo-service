# Luna vs Astra — z2h12 live acceptance (2026-09-23 Asia/Calcutta)

**Tip SHA:** `0cec9d3faf0bf7e0ca30aaed58f2b911c9c0f89c`  
**Branch:** `cursor/material-aeo-recommend-prompt-2b61` (PR #49)  
**Article URI:** https://nik-hil.hashnode.dev/agents-zero-to-hero-12-building-ai-subagents-with-context-isolation.md  
**Domain:** `nik-hil.hashnode.dev`  
**Fixture:** `fixtures/agents-z2h12-live.md` (fresh remote MD, 28933 bytes)  
**Runner:** `/workspace/pr49-z2h12-live-runner.py` with `--rec-retries 1`  
**Internal repairs:** `MAX_RECOMMENDATION_ATTEMPTS = 3` in `aeo_mvp.recommendations.generate_recommendations`  
**auto_publish:** false (both)  
**retrieval_used:** true (both; paid opt-in)

## Outcome summary

| | Luna (`openai-gpt-5.6-luna`) | Astra (`openai-gpt-6-astra`) |
|---|---|---|
| Out dir | `docs/live-luna-20260923-085557` | `docs/live-astra-20260923-090147` |
| Questions | 9 | 9 |
| Opportunities | n/a (failed) | n/a (failed) |
| Multi-section? | n/a | n/a |
| quality_eval | n/a | n/a |
| unsupported / search-imported facts | n/a (no RECOMMENDED) | n/a (no RECOMMENDED) |
| Opportunity ↔ RECOMMENDED consistency | n/a | **Failed validation** (see error) |
| Status | **FAILED** | **FAILED** |

## Luna failure

After discover_queries (17.4s) and measure_visibility (174.5s, retrieval_used=True), `generate_recommendations` raised:

```
LLMError: Major sections deleted in recommended Markdown:
['A useful mental model: delegation as a context firewall',
 'Subagents are a form of context architecture',
 'Subagents versus MCP',
 'Subagents versus skills',
 'The architecture after v0.12',
 'The journey so far',
 'What does the actual demo do?',
 "What's next?",
 'v0.10 — Skills',
 'v0.12 — Subagents',
 'v0.8 — Memory',
 'v0.9 — Compaction']
```

Elapsed in recommendations phase ~145.2s. Outer loop did not re-call (`--rec-retries 1`). Per tip code, up to 3 internal attempts (initial + up to 2 repairs for validation/JSON failures) should have run inside `generate_recommendations` before this raise — so **repair retries appear to have been needed and still insufficient** for section-preservation on this long article (45 sections).

## Astra failure

After discover_queries (45.9s) and measure_visibility (306.2s, retrieval_used=True), `generate_recommendations` raised:

```
LLMError: RECOMMENDED has substantive section edits without matching opportunities for:
['Agents Zero to Hero #12: Building AI Subagents with Context Isolation'].
Emit an opportunity for each applied section change, or leave that section unchanged.
```

Elapsed in recommendations phase ~356.3s. Same outer/inner retry policy. Longer rec phase is consistent with **multiple internal repair attempts** before final raise. Failure mode is opportunity↔RECOMMENDED consistency (title/H1 edited without a matching opportunity) — exactly the class of check the repair path targets.

## Consistency held?

No successful RECOMMENDED/DIFF/report.json for either model, so opportunity↔RECOMMENDED and quality_eval checklists could not be scored on a passing pack. Both runs aborted on deterministic Markdown/opportunity validation after internal repairs.

## Quality checklist (report.json / DIFF)

| Check | Luna | Astra |
|---|---|---|
| opportunity ↔ RECOMMENDED consistency | n/a — no pack | **fail** (validator message) |
| no search-imported / unsupported claims | n/a | n/a |
| quality_eval pass/fail | n/a | n/a |
| repair retries needed? | **yes** (exhausted; still failed) | **yes** (exhausted; still failed) |
| auto_publish false | yes (runner hard-codes False) | yes |

## Notes for PR #49

- Tip correctly clears prior live docs and includes `MAX_RECOMMENDATION_ATTEMPTS = 3` repair path.
- Paid live re-run on z2h12 with Luna then Astra did **not** produce publishable packs under `--rec-retries 1`.
- Distinct failure modes: Luna deleted many major sections; Astra edited H1/title without emitting a matching opportunity.
- Do **not** merge based on this pack. Further prompt/repair work or a controlled outer redraw policy may be needed; multiplying outer retries to 5 would risk many LLM calls and was intentionally avoided.

## Failure detail packs

- Luna: [live-luna-20260923-085557/FAILURES.md](./live-luna-20260923-085557/FAILURES.md)
- Astra: [live-astra-20260923-090147/FAILURES.md](./live-astra-20260923-090147/FAILURES.md)
