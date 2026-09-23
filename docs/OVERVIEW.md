# Hashnode AEO PoC overview

## Product flow (`pipeline.py`)

```python
article = load_hashnode_markdown(...)
queries = discover_queries(article)          # LLM + LLM quality pass
visibility = measure_visibility(...)         # DO web_search plumbing (OBSERVED)
bundle = generate_recommendations(...)       # LLM full-document opportunities + MD
quality = evaluate_quality(...)              # LLM pass/fail
return report(... CURRENT / RECOMMENDED / DIFF ...)
```

## Ownership

See [`ADR-001-llm-semantics.md`](ADR-001-llm-semantics.md).

Recommendations are **full-document** and **question→section**: each gap is edited
in the existing section where it belongs—not dumped into the introduction.

## Honesty limits

- Hashnode Markdown only; **no auto-publish**
- Visibility = DigitalOcean Responses + `web_search` API observation ≠ ChatGPT UI
- `llm_used` / `retrieval_used` from execution / tool evidence only
- Evidence quotes must appear verbatim in CURRENT
- No `**Direct answer:**` template construction in Python
- No YAML/frontmatter or trailing `---` in RECOMMENDED.md
