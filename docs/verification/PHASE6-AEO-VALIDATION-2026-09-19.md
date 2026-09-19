# Phase 6 — AEO validation proof (2026-09-19)

**Verdict: PARTIALLY VALIDATED**  
**Authoritative baseline job:** `e26c5919-0ac5-4aab-86f4-36def39ec882` (CoS live Hashnode)  
**Base main:** `e39855f` (after PR #33 prod-readiness)  
**Paid DigitalOcean web_search this baseline:** **NO** (`paid_do_calls=0`; ADR-026 closed)  
**Live CMS publish:** **NO** (fixture-simulated post-change only)

---

## Executive summary

Yes — a real Hashnode run produces **actionable** Phase 5 / catalog recommendations a site owner can implement.  

**Validated in this Phase 6 package:**

1. Live crawl (20 pages) + `query-set-v3` discovery + Phase 5 content optimization + unpaid drafts  
2. Live **llm-mention** visibility baseline (`openai_compatible`, rate ≈ 0.133 = 8/60)  
3. Three concrete recommendations (brand consolidation, brand-in-copy, heading hierarchy)  
4. Fixture-simulated post-change applying those edits → coverage improvement (`evidence_class=hypothesis`)

**Not live-validated:**

- Paid DO `web_search` AI-search appearance/citation lift  
- Causal claim that edits improve AI citations  
- Live Hashnode CMS publish

---

## Test setup (authoritative CoS baseline)

| Field | Value |
| --- | --- |
| Site | `https://nik-hil.hashnode.dev/` |
| Job | `e26c5919-0ac5-4aab-86f4-36def39ec882` |
| demo_mode | false |
| Pages crawled | **20** |
| Pages optimized | **3** |
| Query-set | `query-set-v3` / id `qs_fc087f4f5ebf` |
| Seed | **3236362228** |
| Fingerprint | `2d79e25bd6f4513556c97f41b7d40851b74887573df594b206b1b221952175ec` |
| Discovery | `query-discovery-v2` |
| Visibility provider | `openai_compatible` (`openai-gpt-4o-mini`) — **llm-mention chat completions ≠ DigitalOcean web_search**; paid retrieval stayed closed (`paid_do_calls=0`) |
| Experiment | `llm_mention` / `llm-mention-v1` |
| Retrieval enabled | **false** |
| Paid DO calls | **0** |
| `paid_retrieval_opt_in` | **false** |
| Content drafts | deterministic skeleton, `paid=false`, generated provenance |

Artifacts (authoritative):

- `docs/verification/artifacts/phase6/PHASE6_COS_BASELINE_EVIDENCE.json`
- `docs/verification/artifacts/phase6/PHASE6_COS_BASELINE_REPORT_EXCERPT.json`
- `docs/verification/artifacts/phase6/PHASE6_COS_BASELINE_SNAPSHOT.json`

Supporting (non-authoritative agent smoke run, demo visibility): `PHASE6_HASHNODE_JOB_*`  
Historical paid DO record only (not Phase 6 remeasure): `PHASE6_PHASE4_AISEARCH_BASELINE.json`

---

## Baseline metrics

### Scores (job e26c5919)

| Metric | Value |
| --- | --- |
| aeo_health | **76.4** |
| technical | 95.0 |
| structured_data | 90.0 |
| answerability | 75.0 |
| content | 69.6 |
| entity | **52.5** (weakest) |

### Visibility (llm-mention only)

| Metric | Value |
| --- | --- |
| llm_mention_rate | **≈ 0.133** (8/60), provenance estimate |
| llm_url_mention_rate | ≈ 0.083 (5/60) |
| AI-search appearance/citation | **not measured** (DO web_search gated off) |

### Content optimization coverage (homepage)

| | |
| --- | --- |
| Gaps | 33 |
| Coverage | queries 20 / covered 6 / gapped 14 / thin 14 / full 3 / partial 3 |
| Page intel | title `Nikhil Ikhar's blog`, **h1=null**, schema `Blog`, entities weak |

---

## Phase 5 briefs after actionability fix

Post-fix regenerated excerpts (fixture HTML + CoS baseline identity):  
`docs/verification/artifacts/phase6/PHASE6_BRIEFS_POST_ACTIONABILITY_FIX.json`

Homepage listing gate: **no** `section:` adds for article probes (permissions / Plan mode); work_queue items cite real `related_gap_ids` with query/evidence in reasons. Catalog R1–R3 remain valid owner actions and align with H1 / brand / Organization / hierarchy ops.

## Phase 5 / catalog recommendation examples

### R1 — Consolidate brand naming

| Field | Value |
| --- | --- |
| Page | `https://nik-hil.hashnode.dev/` |
| Problem | Inconsistent brand strings across titles/pages |
| Evidence | Catalog `REC_CONSOLIDATE_BRAND_NAME`; entity score 52.5; page intel entity `Nikhil Ikhar's blog` vs preferred person/org name |
| Recommendation | Pick one preferred brand spelling; use it consistently in titles and Organization schema |
| Provenance | derived / catalog |
| Expected AEO relevance | Stronger entity consistency for llm-mention probes — **not** a ranking promise |

### R2 — Clarify brand in on-page copy

| Field | Value |
| --- | --- |
| Page | homepage |
| Problem | Low sample llm_mention_rate with weak entity signals |
| Evidence | `llm_mention_rate≈0.133` (8/60); entity 52.5; `REC_CLARIFY_BRAND_IN_COPY` |
| Recommendation | Preferred brand in titles, lead paragraphs, and Organization JSON-LD `name` |
| Provenance | experiment-informed + catalog |
| Expected AEO relevance | Improves brand extractability for mention probes; not citation guarantee |

### R3 — Fix heading hierarchy

| Field | Value |
| --- | --- |
| Page | homepage / series-style surfaces |
| Problem | Heading hierarchy issues (missing/duplicate h1 or level skips) |
| Evidence | page intel `h1=null`; schema_gap / `REC_FIX_HEADING_HIERARCHY`; Phase 5 brief `add h1` |
| Recommendation | One `h1` per page; sequential `h2`→`h3` |
| Provenance | observed missing H1 + catalog |
| Expected AEO relevance | Clearer extractable outline / answerability signals |

Drafts for optimized pages: `status=generated`, `generator=deterministic_skeleton`, `paid=false`.

---

## Website changes tested

| Change | Mode |
| --- | --- |
| Preferred brand in `<title>`, lead, Organization JSON-LD | **fixture-simulated** |
| Single H1 + sequential h2/h3 on homepage | **fixture-simulated** |
| Live Hashnode CMS publish | **not performed** |

Fixtures: `tests/fixtures/phase6/homepage_baseline.html` → `homepage_optimized.html`

---

## Post-optimization results

From `PHASE6_FIXTURE_BEFORE_AFTER.json` (fixture path; seed aligned to baseline fingerprint for coverage compare):

| Page | Baseline gaps | Post gaps | Notable | Evidence class |
| --- | --- | --- | --- | --- |
| Homepage | 2 | 0 | H1 null→`Nikhil Ikhar`; Organization schema present | **hypothesis** |

No live llm-mention or AI-search remeasure after edits.  
Do **not** claim causal visibility improvement.

---

## Limitations

1. Paid DO web_search **not** run (`paid_do_calls=0` by design).  
2. Visibility baseline is **llm-mention**, not AI-search.  
3. No CMS publish — post-change is fixture-only.  
4. Fixture coverage queryset is a brand-focused subset, not a full 20-query remeasure of seed `3236362228`.  
5. Prior Phase 4 DO rates must not be compared as site-quality deltas vs this baseline (different methodology / fingerprints).

---

## Testing

Actionability: `tests/unit/test_brief_actionability.py` (homepage genre gate, related_gap_ids, non-templaty reasons, no cross-article bleed).


```
pytest -q tests/unit/test_phase6_measurement.py \
        tests/unit/test_content_optimization_phase5.py \
        tests/unit/test_job_content_optimization_p1_3.py \
        tests/unit/test_paid_retrieval_opt_in_gate.py

pytest -q -rs
```

```
Focused Phase 5/6 + ADR-026: 86+ passed (see suite)
Full: pytest -q -rs → **423 passed, 1 skipped**
```
Skipped: live DO retrieval optional test (credentials / `AEO_LIVE_RETRIEVAL_TEST` not set).

---

## Safety

ADR-026 remains closed for this baseline. No ungated paid retrieval. Minimal product change: brief gap→work-queue linkage + measurement harness only.

---

## Conclusion

**PARTIALLY VALIDATED**

| Claim | Status |
| --- | --- |
| Live crawl + Phase 5 actionable recs | **validated** (job e26c5919) |
| llm-mention baseline measurable | **validated** |
| Paid DO AI-search visibility | **not live-validated** |
| Post-edit visibility lift | **inconclusive** (fixture hypothesis only) |

Merge recommendation: ready for Architect/Verifier review; leave merge to CoS.
