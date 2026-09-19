# Phase 6 — AEO validation proof (2026-09-19)

**Verdict: PARTIALLY VALIDATED**  
**Branch intent:** Phase 6 real-world AEO validation & optimization proof  
**Base main:** `e39855f` (FINAL MAIN after PR #33 / prod-readiness)  
**Paid DigitalOcean retrieval this run:** **NO** (`paid_retrieval_opt_in=false`; DO key absent)  
**Live CMS publish:** **NO** (fixture-simulated post-change only)

---

## Executive summary

Yes — against the live Hashnode site, the pipeline produces **concrete, page-level optimization recommendations** (problem → evidence → recommended edit → provenance → expected AEO relevance).  

What is proven:

1. Live crawl + discovery + Phase 5 content optimization on `https://nik-hil.hashnode.dev/` with production contracts (SSRF, ADR-026 closed, target identity, provenance).
2. At least three actionable recommendation examples (homepage H1; agent article answer-first rewrite; FAQ/schema fixture edit).
3. A reproducible before/after measurement model (`aeo-before-after-v1`) with honest evidence classes.
4. Fixture-simulated post-change coverage improvements for applied edits (evidence class: **hypothesis**).

What is **not** proven in this environment:

- Live paid AI-search post-change appearance/citation lift (no DO credentials; gate closed by design).
- Causal claim that edits improve AI citations (would require controlled live DO remeasure after CMS publish).

Historical AI-search baseline from Phase 4 live Gate G remains on record (17/20 appeared+cited) and is **not** re-run here.

---

## Test setup

| Field | Value |
| --- | --- |
| Site | `https://nik-hil.hashnode.dev/` |
| Phase 6 live job | `39b9ddcd-0700-4784-b03e-4b8f77d4559c` |
| Pages crawled | 12 (see artifact summary) |
| Pages optimized | 3 (homepage + agents #1 + agents #2) |
| Query count | 20 selected |
| Discovery method | `query-discovery-v2` |
| Query-set version | `query-set-v3` |
| Fingerprint | `506a8f8347c17d950af4cbf09b4e2dcea102ba431853ddda05b6c7c120959df1` |
| Selection seed | 42 |
| Visibility provider (this job) | `demo` fallback via `auto` (no DO / OpenAI keys) |
| Experiment kind | `llm_mention` / synthetic — **not** AI-search proof |
| Retrieval mode | unpaid / non-retrieval |
| Paid retrieval opt-in | **false** |
| ADR-026 gate | **closed** (DO key alone would never authorize spend) |
| Content drafts | deterministic skeleton (`content_provenance=generated`, `paid=false`) |
| Timestamp | job `emitted_at` in report excerpt artifact |

Artifacts:

- `docs/verification/artifacts/phase6/PHASE6_HASHNODE_JOB_SUMMARY.json`
- `docs/verification/artifacts/phase6/PHASE6_HASHNODE_JOB_REPORT_EXCERPT.json`
- `docs/verification/artifacts/phase6/PHASE6_FIXTURE_BEFORE_AFTER.json`
- `docs/verification/artifacts/phase6/PHASE6_RECOMMENDATION_EXAMPLES.json`
- `docs/verification/artifacts/phase6/PHASE6_PHASE4_AISEARCH_BASELINE.json`

Scripts: `scripts/phase6_hashnode_validation.py`, `scripts/phase6_fixture_before_after.py`, `scripts/compare_job_reports.py`  
Methodology: `docs/methodology/BEFORE_AFTER_MEASUREMENT.md`

---

## Baseline metrics

### A) Historical AI-search baseline (Phase 4 live, paid DO — recorded)

| Metric | Value |
| --- | --- |
| Job | `a24c1a42-faac-48da-80ae-c0b608650cbc` |
| Provider | `digitalocean_web_search` |
| Query-set | `query-set-v3` / fp `8547b8bb…` / seed 42 |
| Appeared | **17/20** (rate 0.85) |
| Cited | **17/20** (rate 0.85) |
| Mention estimate | 0.70 (provenance: estimate) |
| Evidence class for Phase 6 reuse | **recorded baseline only** — not a Phase 6 live remeasure |

### B) Phase 6 live job visibility (this environment)

| Metric | Value |
| --- | --- |
| Provider | `demo` (synthetic fallback) |
| Paid retrieval | false |
| AI-search appearance/citation | **not measured** (gate closed; no DO key) |

### C) Phase 6 live content coverage (primary optimized pages)

| Page | Gaps | Coverage summary (queries=20) |
| --- | --- | --- |
| Homepage | 35 | covered 6 / gapped 14 / thin 14 |
| Agents #1 | 29 | covered 11 / gapped 9 / thin 9 |
| Agents #2 | 31 | covered 10 / gapped 10 / thin 10 |

Note: `cite_miss` gaps in this job are enriched from **demo** visibility observations — treat as non-AI-search.

---

## Phase 5 recommendation examples

### R1 — Homepage missing H1

| Field | Value |
| --- | --- |
| Page | `https://nik-hil.hashnode.dev/` |
| Problem | Missing H1 (`schema_gap`, severity high) |
| Evidence | `evidence_class=title_h1`, snippet `h1_missing`, provenance `compatibility` |
| Recommendation | **add h1** — “H1 missing”; pair with answer-first intro about AI agents / MLOps / Python |
| Provenance | derived from gap + page-intel; not a ranking promise |
| Expected AEO relevance | Clearer extractable brand/topic signal for navigational probes |

### R2 — Agents #1 answer-first rewrite

| Field | Value |
| --- | --- |
| Page | `…/agents-zero-to-hero-1-building-an-ai-agent-from-scratch-with-tool-calling` |
| Problem | Thin/partial coverage for selected probes; intro not answer-first enough |
| Evidence | `thin_coverage` rows with `article_body` / derived matched signals |
| Recommendation | **expand meta_description** toward answer-first summary; **rewrite** lead section to state what an agent loop / tool-calling agent is in the first paragraph |
| Provenance | `opt-brief-v1` / derived |
| Expected AEO relevance | Raise `page_coverage` for tool-calling / agent-loop probes via direct answer units |

### R3 — FAQ + schema (fixture-applied, grounded in brief actionability)

| Field | Value |
| --- | --- |
| Page | same Agents #1 URL (fixture path) |
| Problem | Weak FAQ / FAQPage signals for learning-oriented probes |
| Evidence | brief `faq_suggestions` + missing `FAQPage` in schema types on baseline fixture |
| Recommendation | Add visible FAQ block answering agent-loop / tool-calling questions; add `FAQPage` JSON-LD mirroring visible FAQ only |
| Provenance | generated draft remains `content_provenance=generated`; schema suggestion is derived |
| Expected AEO relevance | Improves FAQ extractability and question coverage — **not** a citation guarantee |

Draft honesty: all Phase 6 drafts stamped `generated` / `paid=false`; never fed into observed stores.

Minimal product fix shipped with Phase 6: work-queue items now link **sheet gap types** (`schema_gap`, `thin_coverage`, …) and query-matched gap ids (previously empty `related_gap_ids` due to legacy `metadata`/`query` keys).

---

## Website changes tested

| Change | Mode | Diff intent |
| --- | --- | --- |
| Homepage H1 + short intro | **fixture-simulated** | `tests/fixtures/phase6/homepage_baseline.html` → `homepage_optimized.html` |
| Agents #1 answer-first + FAQ + FAQPage | **fixture-simulated** | `article_agent1_baseline.html` → `article_agent1_optimized.html` |
| Live Hashnode CMS publish | **not performed** | limitation |

---

## Post-optimization results

From `PHASE6_FIXTURE_BEFORE_AFTER.json` (representative queryset, seed 42):

| Page | Baseline gaps | Post gaps | Notable coverage delta | Evidence class |
| --- | --- | --- | --- | --- |
| Homepage | 2 | 1 | H1 null → present | **hypothesis** |
| Agents #1 | 3 | 2 | `full` 2→3; `partial` 1→0 | **hypothesis** |

No live AI-search appearance/citation delta was measured post-edit.  
Do **not** interpret fixture coverage gains as causal citation improvement.

---

## Limitations

1. **No DO credentials** in this environment → ADR-026 gate closed; no live paid remeasure.
2. **No CMS publish** to Hashnode → post-change is HTML-fixture simulation only.
3. Phase 6 live visibility used **demo fallback** — synthetic, not AI-search.
4. Crawl included a Cloudflare `cdn-cgi` URL among page URLs (noise page) — not treated as an optimization target.
5. Some discovered queries reflect off-niche page titles present on-site (e.g. physiology post); briefs can surface them — owners should prioritize on-brand probes.
6. Phase 4 AI-search baseline query-set fingerprint ≠ Phase 6 live discovery fingerprint — not comparable as a quality delta.

---

## Testing

```
pytest -q tests/unit/test_phase6_measurement.py \
        tests/unit/test_content_optimization_phase5.py \
        tests/unit/test_job_content_optimization_p1_3.py \
        tests/unit/test_paid_retrieval_opt_in_gate.py
# → 85 passed

pytest -q -rs
# → 417 passed, 1 skipped
```

Skipped: live DO retrieval test (requires `DO_MODEL_ACCESS_KEY` + `AEO_LIVE_RETRIEVAL_TEST=true`).

## Safety / non-regression scope

Phase 6 does **not** redesign P0/P1 prod-readiness. Touches:

- `content/brief.py` gap→work-queue linkage (minimal actionability fix)
- new `measurement/` module + scripts + fixtures + docs + tests

ADR-026, SSRF, API auth, OpenAI fail-closed, atomic claim, target identity, provenance, crawl honesty, content taxonomy remain covered by existing suite.

---

## Conclusion

**PARTIALLY VALIDATED**

- Actionable Phase 5 recommendations: **validated** on live Hashnode (non-paid path).  
- Implement → measure loop: **validated** for content coverage via fixtures; **not validated** for live AI-search citation lift.  
- Causal AEO visibility improvement: **inconclusive** (no live post-change DO run).

Merge recommendation for CoS: **ready for Architect/Verifier review** — do not claim full end-to-end citation ROI proof.
