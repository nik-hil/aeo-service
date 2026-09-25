---
name: aeo-pr-hygiene
description: Use when opening or updating a pull request on aeo-service.
---
# PR hygiene

## PR body must include
1. Goal (one sentence)
2. What changed (paths)
3. How to test (`pytest -q`, optional Gradio)
4. Paid/live: default off unless user authorized
5. Explicit **Do not merge** unless the user asked to merge

## Prefer
- Small focused PRs
- Fixture-friendly demos
- Link `docs/ADR-001-llm-semantics.md` when changing ownership boundaries

## Avoid
- Drive-by refactors unrelated to the goal
- Committing live keys or huge binary dumps without ask
