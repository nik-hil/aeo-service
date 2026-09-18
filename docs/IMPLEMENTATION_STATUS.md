# Implementation Status — AEO MVP Backend

**Date:** 2026-09-18 (IST)  
**Formula / protocol:** `health-v1` · `llm-mention-v1` · `rec-catalog-v1`  
**P1 status:** Implemented 2026-09-18 (AI crawlers, site understanding, query discovery, retrieval stubs, enriched recs, executive summary, signal classification).  
**Package:** `aeo_mvp` (`src/` layout)

## What works

| Phase | Status | Notes |
| --- | --- | --- |
| 0 Scaffold | Done | `pyproject.toml`, config, logging, SQLAlchemy models, `create_all`, FastAPI app |
| 1 Crawler | Done | robots-respecting live crawl; demo fixtures for `https://demo.example/`; caps 25/2/5s; UA per D012 |
| 2 Analyzers | Done | technical, content (+answerability checks), entities, structured_data → `analysis_evidence` |
| 3 Scoring | Done | `health-v1` weighted mean; `score_components` persisted with breakdowns |
| 4 Recommendations | Done | `rec-catalog-v1`, impact×effort, evidence-linked ranks |
| 5 Visibility | Done | `AIVisibilityProvider`; `DemoProvider` (deterministic); `OpenAICompatibleProvider` (optional key) |
| 6 Pipeline + API | Done | Full orchestrator; `POST/GET /api/v1/jobs`, report, pages; `GET /health`; BackgroundTasks |
| 7 Tests | Done | Unit + analyzer + demo E2E bit-stability + API TestClient — `pytest` green |
| P1-A AI crawlers | Done | `analyzers/ai_crawlers.py` → report `ai_crawler_access` (allow ≠ visibility) |
| P1-B Site understanding | Done | `understanding/site.py` + `site_profiles`; LLM default off |
| P1-C Query discovery | Done | `queries/discovery.py`; demo keeps fixture prompts for bit-stability |
| P1-D Retrieval interface | Done | `retrieval_base.py`, Perplexity stub (no fake metrics), competitors |
| P2 DigitalOcean web_search | Done | `DigitalOceanWebSearchProvider`; PSL `registrable_domain` (private domains ON); `TargetSiteIdentity` / `domain-match-v1`; ai-search metrics/report; mocked tests |
| P3 SiteProfile + query discovery | Done | Evidence-first `site-profile-v1`; genre vs industry; `query-discovery-v1` / `query-set-v2`; diagnostic gate; paid retrieval opt-in; Hashnode offline fixtures; ADRs 024–026 |
| P1-E Enriched recommendations | Done | problem/action/pattern/validation + evidence snippets |
| P1-F Executive summary | Done | `executive_summary` + `page_findings` on report |
| P1-G Signal classification | Done | `docs/methodology/SIGNAL_CLASSIFICATION.md` (health-v1 immutable) |
| Phase 3–4.1.1 Query intelligence | Done | `query-discovery-v2` / `query-quality-v1` / `query-set-v3`; provenance trust boundary |
| Phase 5 Content optimization | Done | `page-intelligence-v1` → gaps → brief → draft; `POST /api/v1/content-optimization`; paid LLM/DO default OFF |

### Demo E2E (verified locally)

- No API keys / no live network for demo crawl or DemoProvider
- Two demo runs → identical health score and visibility rates
- Sample demo health (fixtures as of 2026-09-18): **87.9**
  - technical 100.0 · content 57.5 · entity 92.5 · structured_data 100.0 · answerability 100.0
- Visibility (synthetic): mention **0.4** (6/15), citation **≈0.133** (2/15), coverage **0.6** (3/5)
- Report includes methodology, caveats, scores, findings, enriched recommendations, experiment (`experiment_kind=llm_mention`), plus P1 sections: `ai_crawler_access`, `site_understanding`, `discovered_queries`, `executive_summary`, `page_findings`

### How to run

```bash
cd /workspace/aeo-mvp
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
pytest -q
uvicorn aeo_mvp.api.app:app --host 127.0.0.1 --port 8000
```

See root `README.md` and `examples/`.

## Known gaps / non-goals (MVP)

1. **No Alembic migrations** — `Base.metadata.create_all` only (acceptable per blueprint).
2. **Live crawl not exhaustively integration-tested** against real sites in CI (unit coverage for robots/same-host; live path exists).
3. **OpenAICompatibleProvider** not exercised against a live API in default CI (skipped cleanly without key).
4. **No auth / multi-tenant / frontend / billing** (explicit out of scope).
5. **JS-rendered SPA sites** — heuristics only; no headless browser.
6. **Robots parser** is minimal (UA groups + Allow/Disallow prefixes); not a full robots.txt RFC implementation.
7. **BackgroundTasks** run in-process — process restart drops in-flight jobs; no Redis/Celery queue.
8. **Report provenance map** is embedded per score/metric field; no separate top-level `provenance` object beyond field labels.
9. **Verifier sign-off** (`docs/verification/`) is a separate role — this status is engineer delivery, not Verifier certification.
10. **Content score on demo** intentionally mid-range (thin pricing page, heading skips) so recommendations stay interesting.

## Honesty reminders (product)

- Visibility rates are **estimates** from finite experiments, not engine rankings.
- API observations ≠ consumer ChatGPT / Gemini / Perplexity UI.
- Health does **not** include visibility rates as inputs.
