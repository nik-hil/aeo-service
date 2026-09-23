# ADR-001: LLM owns semantics; Python owns plumbing

## Status

Accepted (Hashnode AEO PoC redesign on PR #47).

## Decision

Semantic work is performed by the DigitalOcean Inference LLM:

- Question discovery (5–10 realistic user questions)
- Question quality validation
- Opportunity analysis (answerability, evidence, target heading, recommended change)
- Full `recommended_markdown` generation
- Quality evaluation of questions + recommendation

Python performs only:

- Deterministic fence-aware Markdown parse
- JSON/schema validation, dedupe, length/count clamps
- DigitalOcean Responses + `web_search` **plumbing** (mention/citation/target-domain rates)
- Safety checks (title preserved, sections not deleted, evidence quotes in original,
  headings exist, no duplicate Direct-answer blocks, DIFF)
- Artifacts + Gradio labels (**OBSERVED** vs **LLM-GENERATED**)

## Rejected approaches

- Heading→question templates (`What is <heading>?`, `How does <heading> work?`)
- Token / TF-IDF semantic scoring and round-robin section selection
- Building RECOMMENDED.md via `**Direct answer:**` string templates
- Multi-provider visibility abstractions, job queues, DB, CMS auto-publish
- Multi-key credential fallback chains (`OPENAI_API_KEY`, `DO_MODEL_ACCESS_KEY`, …)

## Consequences

- No heuristic “offline” question path: `AEO_LLM_API_KEY` is required for analysis
  (tests inject mocks).
- `--live` / non-`dry_run` enables paid `web_search`; `retrieval_used` flips only on
  actual tool evidence.
- Model selection is exclusively `AEO_LLM_MODEL` (see `docs/MODELS.md`).
