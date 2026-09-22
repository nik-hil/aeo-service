# P45 H1 dual-model COMPARISON

- **Tip SHA:** `a556c0044277b2afc40b2f60befd70a2a802ad8b`
- **seed_url:** https://nik-hil.hashnode.dev/agents-zero-to-hero-1-building-an-ai-agent-from-scratch-with-tool-calling.md
- **crawl_source:** `fixture_due_to_cloudflare_403`
- **fixture_path:** `docs/aeo-p45-h1-fix-20260922-182803/agents-z2h_current.md`
- **live_http_status:** 403
- **paid flags:** AEO_PAID_RETRIEVAL_OPT_IN=true, provider=digitalocean_web_search, draft_paid=true

## Jobs

| Role | Model | Job ID | Status | VERDICT | llm_used | stub | elapsed_s |
|------|-------|--------|--------|---------|----------|------|-----------|
| baseline | `openai-gpt-4o-mini` | `8b0b8423-bf2c-4233-928b-aac8d0e09077` | completed | **PASS** | True | False | 137.88 |
| stronger | `openai-gpt-4o` | `6f715889-2679-476e-a352-8df25e202500` | completed | **PASS** | True | False | 100.76 |

## Section targets selected

### baseline (`openai-gpt-4o-mini`)
- targets: `['section:The finish tool', 'section:The finish tool', 'section:The finish tool', 'section:The finish tool']`
- distinct: `['section:The finish tool']`
- repeated_section_target: True
- mega_section_selected: False

### stronger (`openai-gpt-4o`)
- targets: `['section:The complete flow', 'section:The complete flow', 'section:The complete flow', 'section:The complete flow']`
- distinct: `['section:The complete flow']`
- repeated_section_target: True
- mega_section_selected: False

## Dumping gone?

- baseline dumping_gone: **True** (hits=[], ratio=[])
- stronger dumping_gone: **True** (hits=[], ratio=[])

## CURRENT vs RECOMMENDED / publishability

| Role | current_ne_recommended | current_chars | recommended_chars | diff_bytes | paid_llm | method |
|------|------------------------|---------------|-------------------|------------|----------|--------|
| baseline | True | 11791 | 12608 | 1880 | True | None |
| stronger | True | 11791 | 11806 | 777 | True | None |

## Model differences

- Same seed URL and crawl body; only LLM model differs (`openai-gpt-4o-mini` vs `openai-gpt-4o`).
- Baseline targets: ['section:The finish tool', 'section:The finish tool', 'section:The finish tool', 'section:The finish tool']
- Stronger targets: ['section:The complete flow', 'section:The complete flow', 'section:The complete flow', 'section:The complete flow']
- Baseline VERDICT: PASS
- Stronger VERDICT: PASS

## Repeated targets note

Both models produced **ready** `rewrite_section` ops against a **real H1 heading**
(not a mega-corpus / full-article span). However each run repeated the *same*
heading across multiple gap/query ops:

- baseline → always `section:The finish tool` (4×)
- stronger → always `section:The complete flow` (4×)

So: **dumping / mega-section regression = gone**; **cross-query diversity of
section targets** is still limited for this seed+query set (selection_seed=42).
`repeated_section_target=true` is recorded honestly in each acceptance_report.json.


## Paid DO web search evidence

Visibility experiment used `provider=digitalocean_web_search` with `retrieval_enabled=true`
for both models (11 observations each; search_queries + source_urls present).

Note: top-level `report.paid_retrieval` / `content_optimization.paid_retrieval` stayed
**false** in this build; do not treat that flag alone as proof web search was off.
See `paid_do_web_search_evidence` in each `acceptance_report.json`.
