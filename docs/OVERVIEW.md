# Hashnode AEO PoC overview

## Product flow (`pipeline.py`)

```python
article = load_hashnode_markdown(...)
queries = discover_queries(article)
visibility = measure_visibility(article, queries)
opportunities = analyze_opportunities(article, queries, visibility)
recommended = generate_recommendations(article, opportunities)
return report(...)
```

## Honesty limits

- Hashnode Markdown only — no WordPress / Medium adapters.
- No auto-publish to Hashnode or any CMS.
- Visibility uses DigitalOcean Responses API + server-side `web_search` only.
- API observations ≠ consumer ChatGPT / Gemini / Perplexity UI.
- `llm_used` / `retrieval_used` reflect **actual execution / tool evidence**, not config.
- Recommendations require evidence quotes that appear in the article when claimed.
- H1 is never treated as a mega-section corpus for body edits when H2+ exist.
- Edits are spread across sections (no dumping all ops on one heading).

## Artifacts

- `CURRENT.md` — input Markdown
- `RECOMMENDED.md` — grounded edits applied under target headings
- Diff shown in Gradio
