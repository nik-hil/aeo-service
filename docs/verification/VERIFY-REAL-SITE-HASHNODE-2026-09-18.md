# Independent AEO Verification — Real Site Hashnode

**Verifier role:** Independent AEO Verifier (do not trust Engineering narrative)  
**Signed at:** 2026-09-18 11:26:18 IST  
**Job ID:** `47b0fca2-d183-444a-b07f-77870b0c0d14`  
**Target URL:** `https://nik-hil.hashnode.dev/agents-zero-to-hero-1-building-an-ai-agent-from-scratch-with-tool-calling`  
**Repo / DB:** `/workspace/aeo-mvp` · `aeo_mvp.db`  
**Engineering claims reviewed (not trusted a priori):**  
- `docs/verification/REAL_SITE_HASHNODE_2026-09-18.md`  
- `docs/verification/REAL_SITE_47b0fca2.json` (sha256 prefix `77298cde36f02cd3`, 55824 bytes)

## Overall: **PASS**

Independent sources used: SQLite `aeo_mvp.db` (jobs/pages/score_components/experiment_*/recommendations/reports/site_profiles), product scoring code `src/aeo_mvp/scoring/health.py`, methodology `docs/methodology/METRICS.md`, SSRF `src/aeo_mvp/security/ssrf.py` + `tests/unit/test_ssrf.py`. Product source was **not** modified.

---

## Criterion 1 — Live crawl job: **PASS**

| Field | DB (`jobs` / `pages`) | JSON artifact |
| --- | --- | --- |
| status | `completed` | `completed` |
| demo_mode | `0` / false | `false` |
| pages | **15** (all status_code=200, fetch_error=NULL) | `pages_crawled`: 15 |
| base_url | hashnode seed article | matches |
| created_at / completed_at | `2026-09-18T05:54:05+00:00` → `05:54:07+00:00` (11:24:05–11:24:07 IST) | `emitted_at` `2026-09-18T05:54:07+00:00` |

Live-crawl evidence (not demo pages): HTML bodies present for all 15 rows (`html` length min **12095**, max **264133**). Titles include real article titles (e.g. “Build an AI Agent From Scratch…”, “Building a Secure Shell…”).

**Verdict:** PASS — completed live crawl, `demo_mode` false, `pages > 0`.

---

## Criterion 2 — Health-v1 recompute: **PASS**

Authoritative weights (`METRICS.md` / `WEIGHTS` in `health.py`):

`H = clamp(0.25·T + 0.25·C + 0.20·E + 0.15·S + 0.15·A)`

| Source | T | C | E | S | A | H |
| --- | --- | --- | --- | --- | --- | --- |
| JSON `scores.*` (1dp) | 95.0 | 70.7 | 32.5 | 90.0 | 75.0 | **72.7** reported |
| Independent from JSON comps | | | | | | raw **72.675** → **72.7** |
| DB `score_components` | 95.0 | 70.666… | 32.499… | 90.0 | 75.0 | DB health **72.666…** → **72.7** 1dp |
| `health_from_components(**DB)` | | | | | | **72.666…** |

`formula_version` = `health-v1` in DB and JSON. Abs(reported − recomputed) = 0.0 at 1dp (< 0.1 tolerance).

**Verdict:** PASS.

---

## Criterion 3 — Experiment honesty: **PASS**

| Field | DB | JSON / Eng MD |
| --- | --- | --- |
| experiment_kind | `llm_mention` | `llm_mention` |
| retrieval_enabled | `0` / false | `false` |
| provider_name | `demo` | `demo` |
| metric provenance | `synthetic_demo` (all 3 metrics) | same |

Caveats present in report JSON (and Eng MD), e.g.:

- “LLM mention metrics … **not AI search visibility** or engine rankings.”
- “Chat-completions / LLM mention probes (`retrieval_enabled=false`) are **NOT equivalent to AI search visibility**.”
- “API-based observations are not equivalent to consumer ChatGPT, Gemini, or Perplexity UI results.”

Grep of report text: phrases about “AI search visibility” appear only in **denial/caveat** contexts; recommendation copy says “not a ChatGPT ranking promise.”

**Verdict:** PASS — honestly labeled llm_mention / non-retrieval / not AI-search visibility.

---

## Criterion 4 — Recommendations cite evidence: **PASS**

DB: 6 recommendations; each has `evidence_ids_json` non-empty and `details_json.evidence_snippets` non-empty.

Examples (from JSON artifact, cross-checked with DB):

1. **REC_ADD_JSONLD_ORG** — `evidence_ids` include `2cee7220-…` (ENTITY_ORG_SIGNAL “Footer org/copyright hint only”), `0e689ee7-…` (SD_ID_SAMEAS); `affected_urls`: seed article URL.
2. **REC_CONSOLIDATE_BRAND_NAME** — evidence ENTITY_BRAND_CONSISTENCY / ENTITY_AMBIGUITY with data_preview ratios.
3. **REC_FIX_HEADING_HIERARCHY** — 15 `evidence_ids`, 15 `affected_urls` across series/tag/home pages.

Note: **REC_IMPROVE_CITABLE_URLS** has evidence (`TECH_PAGE_SUCCESS_RATE`) but `affected_urls=[]` — still cites evidence IDs/snippets.

**Verdict:** PASS.

---

## Criterion 5 — SSRF still blocks localhost: **PASS**

- Re-ran: `.venv/bin/python -m pytest tests/unit/test_ssrf.py -v` → **13 passed**, 0 failed (includes `http://localhost/`, `http://127.0.0.1/`, `http://[::1]/`, private RFC1918, metadata IP, `file://`, `ftp://`).
- Direct call `assert_safe_public_url(...)`:
  - `http://127.0.0.1/` → `SSRFError: Resolved address is not public: 127.0.0.1`
  - `http://localhost/` → `SSRFError: Blocked hostname: localhost`
  - Target Hashnode URL → **allowed**

**Verdict:** PASS — substituting localhost for the job URL would be rejected by SSRF policy.

---

## Criterion 6 — Limitations honest (Verifier notes): **PASS**

Verified as **accurate** (not merely restated):

1. **Demo visibility provider on a live crawl** — crawl is live (`demo_mode=false`, real HTML), but visibility experiment used `provider_name=demo` with `synthetic_demo` rates (0/30 mentions). Must not be read as live LLM/API search observations.
2. **Category misguess** — `site_profiles.industry_category_guess = project_management` for an AI/engineering blog; discovered queries include “compare to other **project management tools**” and “best **project management** tool” — heuristic pollution confirmed in DB/JSON.
3. **No retrieval-enabled run** — `retrieval_enabled=false`; no competitor citation / AI-search graph.
4. Eng Limitations §1–4 match DB state; Verifier confirms they are not overselling.

**Verdict:** PASS — limitations disclosed and independently confirmed.

---

## Cross-checks summary

| Check | Result |
| --- | --- |
| Job row exists in `aeo_mvp.db` | Yes |
| Artifact job_id matches | Yes |
| `demo_mode` false + pages>0 | Yes (15) |
| Health math | Yes (72.7) |
| Experiment not marketed as AI-search visibility | Yes |
| Recs have evidence | Yes (6/6) |
| SSRF localhost blocked | Yes (tests + direct) |

## Top issues / residual risks (non-FAIL)

1. Visibility numbers are **synthetic_demo** despite live crawl — easy to misread dashboards if UI is unclear.
2. **project_management** industry misguess skews query templates.
3. One recommendation (`REC_IMPROVE_CITABLE_URLS`) lacks `affected_urls` (evidence still present).

## Signature

```
verifier: Independent AEO Verifier (executor subagent)
signed_at: 2026-09-18 11:26:18 IST
overall: PASS
job_id: 47b0fca2-d183-444a-b07f-77870b0c0d14
db: /workspace/aeo-mvp/aeo_mvp.db
artifact_json_sha256_16: 77298cde36f02cd3
method: independent DB read + health_from_components recompute + pytest SSRF + assert_safe_public_url
product_source_modified: false
```

---

*End of independent verification report.*
