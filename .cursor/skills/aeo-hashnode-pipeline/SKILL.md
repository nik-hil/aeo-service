---
name: aeo-hashnode-pipeline
description: Use when implementing or changing the Hashnode Markdown AEO pipeline (load → questions → visibility → recommendations → quality → artifacts).
---
# Hashnode AEO pipeline

## Flow (`src/aeo_mvp/pipeline.py`)
1. Load Hashnode Markdown (not HTML-as-source-of-truth).
2. LLM: discover queries + quality pass (`queries.py`).
3. OBSERVED visibility via DO Responses + `web_search` (`visibility.py`).
4. LLM: full-document opportunities + complete RECOMMENDED.md (`recommendations.py`).
5. LLM: quality evaluation (`evaluation.py`).
6. Emit CURRENT.md / RECOMMENDED.md / DIFF / SUMMARY.md / report.json; Gradio under `ui/gradio/`.

## Invariants
- `docs/ADR-001-llm-semantics.md` ownership split.
- No auto-publish.
- Evidence quotes verbatim from CURRENT.
- Opportunity rows match applied RECOMMENDED section edits.
- Intro is not the default edit dump.

## Done checks
- `pytest -q` and `python -m compileall -q src ui`
- Artifacts labeled OBSERVED vs LLM-GENERATED
- No secrets in outputs
