# AEO Verifier — Post-Review Independent Sign-off

**Report ID:** `VERIFY-POST-REVIEW-2026-09-18`  
**Verifier role:** Independent AEO Verifier (do not trust Engineering claims)  
**Repo:** `/workspace/aeo-mvp`  
**Generated:** 2026-09-18 11:09 IST (Asia/Calcutta)  
**Environment:** isolated SQLite `AEO_DATABASE_URL=sqlite:////tmp/aeo_verify_post_review.db`, `AEO_DEMO_MODE=true`  
**Product source modified:** No (docs/verification writes only)

## Overall: **PASS**

All six acceptance criteria passed with independently re-run evidence.

---

## Criterion 1 — pytest (46+ passed): **PASS**

**Command:**
```bash
cd /workspace/aeo-mvp
AEO_DATABASE_URL=sqlite:////tmp/aeo_verify_post_review.db AEO_DEMO_MODE=true \
  .venv/bin/python -m pytest -q
```

**Result:**
```
..............................................                           [100%]
46 passed, 2 warnings in 0.70s
```

**Actual count:** **46 passed** (meets ≥46). Collect-only also reports `46 tests collected`.

Warnings are Starlette/httpx TestClient deprecation only; not failures.

---

## Criterion 2 — Independent verification script: **PASS**

**Command:**
```bash
cd /workspace/aeo-mvp
.venv/bin/python scripts/run_independent_verification.py
echo EXIT:$?
```

**Result:**
- Script present: `scripts/run_independent_verification.py`
- Exit code: **0**
- Output: `Wrote /workspace/aeo-mvp/docs/verification/VERIFY-COMPLETE-DRAFT.md overall=PASS`

Harness internal sections (from regenerated draft): `import_app`, `demo_job`, `p1_report_sections`, `health_recompute`, `observation_flags`, `no_false_ai_search_claims`, `pytest_ssrf_scoring_p1` — all **PASS**.

---

## Criterion 3 — Demo job report keys: **PASS**

**Method:** Independent orchestrator path (not relying on Engineering narrative). Created demo job against isolated DB:

```text
JOB_ID fad7e5a2-a146-49e7-9371-78489dca2520
STATUS completed
```

Report artifact: `/tmp/aeo_demo_report_post_review.json`

| Required field | Observed | Verdict |
|---|---|---|
| `experiment.experiment_kind` | `llm_mention` | PASS |
| `experiment.retrieval_enabled` | `false` | PASS |
| `experiment.llm_mention_rate` | present `{value:0.4, numerator:6, denominator:15, provenance:synthetic_demo}` | PASS |
| Not marketed as “AI search” | `provider_capabilities_notes`: “Non-retrieval LLM mention provider; not AI search visibility.”; caveats explicitly deny AI-search equivalence; key `ai_mention_rate` **absent** | PASS |
| `ai_crawler_access` | present; `agents` length **10** | PASS |
| `site_understanding` | present; `organization_brand=AcmeFlow` | PASS |
| `discovered_queries` | present; `queries` length **10** | PASS |
| `executive_summary` | present; keys `data_provenance`, `major_caveats`, `overall_health`, `strongest_areas`, `top_3_actions`, `weakest_areas` | PASS |
| Enriched recommendations | 5 recs; see below | PASS |

**Experiment keys observed:**  
`experiment_kind`, `llm_mention_rate`, `llm_url_mention_rate`, `model_id`, `observations_count`, `protocol_version`, `provider_capabilities_notes`, `provider_name`, `query_coverage`, `retrieval_enabled`

### What “enriched” means (from live payload)

Recommendation objects include **more than** basic `code` / `priority_score` / `rank` / `title` / `rationale`. Live `recommendations[0]` keys:

```text
affected_urls, code, effort, evidence_ids, evidence_snippets, finding_ids,
id, impact, implementation_pattern, priority_score, problem, rank, rationale,
recommended_action, title, validation_method, why_it_matters
```

**Enrichment extras** (beyond basic ranking fields), matching `src/aeo_mvp/recommendations/enrichment.py`:

- `problem`, `why_it_matters`, `recommended_action`
- `implementation_pattern`, `validation_method`
- `affected_urls`, `evidence_snippets` (id/code/message/severity/data_preview)
- plus linkage: `evidence_ids`, `finding_ids`, and scoring fields `effort`, `impact`

Sample first rec: `code=REC_CONSOLIDATE_BRAND_NAME`, has non-empty `recommended_action`, `evidence_snippets`, `affected_urls=["https://demo.example/"]`.

Caveats on report (honesty of metric labeling):
```text
"LLM mention metrics are sample estimates from controlled llm-mention-v1 experiments, not AI search visibility or engine rankings."
"Chat-completions / LLM mention probes (retrieval_enabled=false) are NOT equivalent to AI search visibility."
"API-based observations are not equivalent to consumer ChatGPT, Gemini, or Perplexity UI results."
```

---

## Criterion 4 — SSRF: **PASS**

**Tests exist:** `tests/unit/test_ssrf.py`

Parametrized blocks include: `localhost`, `127.0.0.1`, `10.0.0.1`, `192.168.1.1`, `172.16.5.5`, link-local metadata `169.254.169.254`, `[::1]`, `file://`, `ftp://`. Also redirect-to-private coverage via `test_redirect_target_private_ip_rejected` and `test_fetch_url_blocks_redirect_to_private`.

**Targeted run:**
```bash
.venv/bin/python -m pytest -q tests/unit/test_ssrf.py -v
```
```
tests/unit/test_ssrf.py .............                                    [100%]
13 passed, 2 warnings in 0.03s
```

Included in full suite (46 passed) as well.

**Spot-check protection code:** `src/aeo_mvp/security/ssrf.py` (~174 lines)

- `_BLOCKED_HOST_LABELS` includes `localhost`
- `_ip_is_public` rejects loopback / link-local / multicast / reserved / **private** (`ip.is_private`) and `169.254.0.0/16`
- `assert_safe_public_url` / `is_obviously_unsafe_url` used for allow-policy

---

## Criterion 5 — Honesty (OpenAI chat ≠ consumer AI search UI): **PASS**

Independent grep across README, docs, report caveats, methodology, and visibility providers found **honest caveats**, not equivalence claims.

**Affirmative disclaimers (examples):**

- `README.md` L5: does **not** reproduce ChatGPT / Gemini / Perplexity ranking; metrics are sample estimates.
- `README.md` L59: “API observations are **not** consumer ChatGPT UI results.”
- `docs/methodology/AI_VISIBILITY.md`: **Forbidden** labeling OpenAI-compatible `/chat/completions` (no tools) as AI search visibility; “LLM mention ≠ AI search visibility.”
- `docs/IMPLEMENTATION_STATUS.md`: “API observations ≠ consumer ChatGPT / Gemini / Perplexity UI.”
- Live report caveats (Criterion 3) and `provider_capabilities_notes` reinforce non-equivalence.
- `src/aeo_mvp/visibility/openai_compatible.py`: “This is an LLM mention experiment, NOT AI search visibility.”

**No FAIL-triggering claim** found that OpenAI chat completions / API = ChatGPT / Gemini / Perplexity consumer search UI. Mentions of those products appear as **prohibitions** or research framing, not product equivalence.

---

## Criterion 6 — Signed report artifacts: **PASS** (this document + JSON)

- Markdown: `docs/verification/VERIFY-POST-REVIEW-2026-09-18.md` (this file)
- JSON summary: `docs/verification/VERIFY-POST-REVIEW-2026-09-18.json`

---

## Cleanup

- Port **8000**: free (no leftover uvicorn; none started for this verification — used in-process orchestrator).
- Product source: untouched.

## Top issues

None. Overall **PASS**.
