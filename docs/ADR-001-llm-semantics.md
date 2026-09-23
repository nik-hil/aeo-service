# ADR-001: LLM owns semantics; Python owns plumbing

## Status

Accepted (Hashnode AEO PoC redesign on PR #47).

## Decision

Semantic work is performed by the DigitalOcean Inference LLM:

- Question discovery (5–10 realistic user questions)
- Question quality validation
- **Full-document** opportunity analysis + complete `recommended_markdown`
- Quality evaluation of questions + recommendation

### Full-document question → section recommendations

The recommendation engine must read the **entire** CURRENT article before editing.
For each selected question: identify the gap → choose the logically relevant
**existing** section (`target_heading`) → apply a minimal grounded edit there.
The introduction is **not** the default place for improvements. Different questions
should touch different sections when evidence supports it. Opportunities carry:

`question`, `gap`, `target_heading`, `recommended_change`, `evidence_quote`
(verbatim from CURRENT).

`RECOMMENDED.md` is the complete improved article only (no frontmatter / trailing
`---`, no Direct-answer templates, no invented facts).

Python performs only:

- Deterministic fence-aware Markdown parse
- JSON/schema validation, dedupe, length/count clamps
- DigitalOcean Responses + `web_search` **plumbing** (mention/citation/target-domain rates)
- Safety checks (title preserved; headings not deleted; **section order preserved**;
  evidence quotes in CURRENT; headings exist; no frontmatter/`---`; no duplicate
  Direct-answer blocks; lightweight anti-intro-concentration when opportunities
  claim non-intro sections; DIFF)
- Artifacts + Gradio labels (**OBSERVED** vs **LLM-GENERATED**)

## Rejected approaches

- Heading→question templates (`What is <heading>?`, `How does <heading> work?`)
- Token / TF-IDF semantic scoring and round-robin section selection
- Intro-only / lead-paragraph-only optimization
- Building RECOMMENDED.md via `**Direct answer:**` string templates
- Multi-provider visibility abstractions, job queues, DB, CMS auto-publish
- Multi-key credential fallback chains (`OPENAI_API_KEY`, `DO_MODEL_ACCESS_KEY`, …)

## Consequences

- No heuristic “offline” question path: `AEO_LLM_API_KEY` is required for analysis
  (tests inject mocks).
- `--live` / non-`dry_run` enables paid `web_search`; `retrieval_used` flips only on
  actual tool evidence.
- Model selection is exclusively `AEO_LLM_MODEL` (see `docs/MODELS.md`).
- Prior `docs/live-*` acceptance folders are removed from the branch when prompts
  change; CoS re-runs paid live and pushes fresh artifacts.
