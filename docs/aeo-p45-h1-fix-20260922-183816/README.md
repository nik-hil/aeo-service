# P45 H1 fix — dual-model paid LLM + paid DO web search acceptance

- **Tip SHA:** `a556c0044277b2afc40b2f60befd70a2a802ad8b`
- **PR:** #45 (`cursor/substantive-content-opt-e95e`)
- **seed_url:** https://nik-hil.hashnode.dev/agents-zero-to-hero-1-building-an-ai-agent-from-scratch-with-tool-calling.md
- **crawl_source:** `fixture_due_to_cloudflare_403`
- **fixture_path:** `docs/aeo-p45-h1-fix-20260922-182803/agents-z2h_current.md`
- **live_http_status:** 403
- **paid flags:** `AEO_PAID_RETRIEVAL_OPT_IN=true`, provider=`digitalocean_web_search`, never demo
- **Baseline model:** `openai-gpt-4o-mini` — job `8b0b8423-bf2c-4233-928b-aac8d0e09077` — status `completed` — VERDICT **PASS**
- **Stronger model:** `openai-gpt-4o` — job `6f715889-2679-476e-a352-8df25e202500` — status `completed` — VERDICT **PASS**

## Layout

- `baseline/` — CURRENT / RECOMMENDED / diff / acceptance_report.json
- `stronger/` — same
- `COMPARISON.md` — section targets, dumping, publishability, model differences
- `COMPARISON_SHORT.md` — one-screen summary

Prior folder `docs/aeo-p45-h1-fix-20260922-182803/` is superseded (web search OFF / no live key).

## Paid DO web search

- Both jobs: `experiment.provider_name=digitalocean_web_search`, `retrieval_enabled=true`, 11 visibility observations each.
- `report.paid_retrieval` flag is false in this build; evidence is under `paid_do_web_search_evidence` in acceptance_report.json.
