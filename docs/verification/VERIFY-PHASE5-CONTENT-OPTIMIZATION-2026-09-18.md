# Independent verification — Phase 5 content optimization (C1–C10)

**Date:** 2026-09-18  
**PR under review (product):** https://github.com/nik-hil/aeo-service/pull/17  
**product_commit_sha (final product code under review):** `53e5d11f44ce7e4f9a2e0100007930eac9e9deff`  
**tip (re-checked):** `bda584f8858a19642bda96e1b256ee13edd24c78` — **differs** from product_commit_sha (tip-only commit adds VERIFY docs onto product PR; `src/` unchanged vs product_commit_sha)  
**Tip at start:** `53e5d11f44ce7e4f9a2e0100007930eac9e9deff` → re-check moved to `bda584f…`  
**Product branch:** `cursor/phase5-content-optimization-ae1e`  
**Base:** `main` @ `28a0b8526f3c76c6116565aa2ef08256201976bd`  
**checklist_version:** `content-optimization-v1`  
**Binding docs (authoritative when conflict):** `docs/methodology/CONTENT_OPTIMIZATION_V1.md` · `docs/architecture/PHASE5_EVALUATOR_GATES.md` (prefer over shorter `docs/methodology/CONTENT_OPTIMIZATION.md`, which defers to V1)  
**Method:** independent code read + full pytest + independent Python probes; Engineering/PR claims not trusted a priori  
**Paid DigitalOcean APIs:** not run  
**Paid LLM inference:** not run  
**Product code changed by Verifier:** none (docs-only VERIFY artifacts on this docs PR)

## Honesty locks (asserted)

- diagnostics ≠ site score / health-v1  
- page_coverage ≠ AI visibility / LLM-mention  
- generated draft ≠ observed evidence / QSQ-EVD / crawl observed stores  

## CoS methodology notes (non-blocking)

1. **Structure / heading heuristic provenance spot-check** — see C1 evidence. One FLAG: structure gap `heading_count=N` stamped `observed` (should be `derived`). Does not block merge.
2. **Binding docs preference** — V1 methodology + Evaluator gates authoritative; short `CONTENT_OPTIMIZATION.md` is a pointer/summary (no material conflict found).

## Overall: **PASS**

Gate table rows are **assert-intent** labels. Test function names are evidence paths only.

| Gate (assert intent) | Result | Blocks merge? |
| --- | --- | --- |
| **C1:** PageIntelligence from source; hostname-scoped; provenance normalize; no invented observed | **PASS** | yes if FAIL |
| **C2:** Provenance enum; draft/generated never → observed / QSQ-EVD | **PASS** | yes if FAIL |
| **C3:** Coverage enum from themes/content; no niche hardcode; not marketed as AI visibility/health | **PASS** | yes if FAIL |
| **C4:** Evidence-backed gaps; deterministic prioritize | **PASS** | yes if FAIL |
| **C5:** opt-brief-v1 cites intel+gaps+queryset versions; retain/rewrite/expand/remove/add + reasons | **PASS** | yes if FAIL |
| **C6:** Grounded draft; unsupported→warnings; paid=False default; Null/skeleton OK | **PASS** | yes if FAIL |
| **C7:** Determinism + freezes held | **PASS** | yes if FAIL |
| **C8:** New URL fetches use SSRF path; no private/metadata bypass | **PASS** | yes if FAIL |
| **C9:** Content VERIFY/dry-run no paid DO inference/retrieval | **PASS** | yes if FAIL |
| **C10:** Full pytest green + Phase 5 tests; no live external site deps | **PASS** | yes if FAIL |

**Merge recommendation:** **PASS** — all blocking gates C1–C10 PASS.

**Pytest (independent on tip `bda584f`, product code = `53e5d11`):** `205 passed, 1 skipped, 0 failed` in 4.10s  
**Phase 5 file:** `42 passed` (`tests/unit/test_content_optimization_phase5.py`)  
**Skipped:** `tests/unit/test_digitalocean_web_search.py::test_live_digitalocean_web_search_optional` (live paid DO; not run)

**Sibling JSON:** `docs/verification/VERIFY-PHASE5-CONTENT-OPTIMIZATION-2026-09-18.json`  
**Does not overwrite:** any `VERIFY-PHASE4*` / `VERIFY-PHASE4.1*` (product tip diff vs main for those paths empty; this docs PR adds only Phase 5 VERIFY files)

---

## Commands run

```bash
git fetch origin pull/17/head
# tip_at_start=53e5d11… → tip_rechecked=bda584f… (VERIFY-only tip move; src/ identical)

pip install -e ".[dev]"
pytest -q
# → 205 passed, 1 skipped, 2 warnings in 4.10s  (on tip bda584f)

pytest tests/unit/test_content_optimization_phase5.py -v
# → 42 passed

git diff 28a0b85...bda584f -- \
  src/aeo_mvp/security/ssrf.py \
  src/aeo_mvp/target_site.py \
  src/aeo_mvp/domains.py \
  src/aeo_mvp/scoring/health.py \
  src/aeo_mvp/visibility/digitalocean_web_search.py \
  src/aeo_mvp/queries/select_v2.py \
  src/aeo_mvp/queries/evidence.py
# → empty (DIFF_BYTES=0)

git diff 28a0b85...bda584f -- docs/verification/VERIFY-PHASE4*
# → empty

# Independent probes + CoS structure/heading provenance spot-check
```

---

## C1 — Page intel — **PASS**

**Assert intent:** `PageIntelligence` from source page HTML; hostname-scoped; missing provenance → compatibility via 4.1.1 normalize; no invented observed facts.

### Evidence

- Code: `src/aeo_mvp/content/page_intel.py` (`extract_page_intelligence`, `_content_prov` → `normalize_provenance`); `target_match_scope="hostname"`; internal links filtered to same host.
- Independent probe: SaaS fixture @ `https://acme-widgets.example/pricing` → `hostname=acme-widgets.example`; docs fixture @ other host scoped separately; empty HTML string stamps `compatibility` (not fabricated observed title/meta); title present → `observed`.
- Evidence path: `test_c1_page_intel_provenance_hostname_scope`, `test_a_page_intelligence_observed_facts_hashnode`, `test_b_provenance_missing_maps_to_compatibility`.

### CoS structure / heading heuristic provenance (non-blocking)

| Signal | Provenance | Verdict |
| --- | --- | --- |
| Heading text (`HeadingNode` from `<h1>`–`<h6>`) | `observed` | **OK** — true crawl extract |
| `answerability_signals` | `derived` | **OK** — heuristic |
| `word_count` signal | `derived` | **OK** |
| Thin-body structure gap (`word_count=N`) | `derived` | **OK** |
| Technical gap `has_main=false` | `observed` | **OK** — DOM landmark absence is crawl extract |
| Structure gap “Fewer than two headings” evidence `heading_count=N` | `observed` | **FLAG** — count/threshold heuristic should be `derived` (`gaps.py`); confirmed with word_count≥120 + single H1 |
| `AnswerUnit.kind` (faq/howto/section) on unit stamped `observed` | unit=`observed` | **NOTE** — heading text is extract; kind label is heuristic (no separate kind provenance field) |
| `limits` (`thin_copy`, `heading_skip`, …) | unstamped strings | **OK** — not stamped `observed` |

FLAG does **not** invent missing page facts as observed; does **not** fail C1 (host scope + missing→compatibility). CoS honesty note only.

---

## C2 — Provenance — **PASS**

**Assert intent:** Enum `observed|derived|compatibility|(generated for drafts)`; draft/generated never enters observed evidence / QSQ-EVD / crawl observed stores.

### Evidence

- `normalize_provenance(None|"")` → `compatibility`; explicit values preserved.
- Draft `to_dict()` hard-codes `content_provenance: "generated"`; `UnsupportedClaim*` default `generated`; `AnswerUnit.to_answer_block()` maps `generated` → `compatibility` (never observed).
- No `content_provenance="observed"` assignment in content package; `queries/evidence.py` and `quality.py` do not import `aeo_mvp.content`.
- Brief caveat documents: “Draft text is generated — never feed into QSQ-EVD as observed.”
- Pipeline gap evidence provenances observed were page-derived/`compatibility`/`derived` only — never `generated` stamped as observed.
- Evidence path: `test_c2_provenance_includes_generated_no_draft_to_observed`, `test_r_generated_draft_never_observed`, `test_honesty_diagnostics_not_health_generated_not_observed`.

---

## C3 — Coverage — **PASS**

**Assert intent:** query×page coverage from snapshot themes/content (`full|partial|thin|absent|mismatched`); no niche/hostname hardcode; coverage not marketed as AI visibility/health.

### Evidence

- `page_coverage_status` / `assess_coverage_by_query` in `gaps.py`; report flags `coverage_is_not_ai_visibility` / `coverage_is_not_health_v1`; matrix cells set `not_ai_visibility` / `not_health_v1`.
- Independent probe: multi-level enum on SaaS fixture; zero `hashnode` string matches under `src/aeo_mvp/content/`.
- Evidence path: `test_c3_coverage_from_snapshot_themes_no_niche_hardcode`, `test_d_coverage_levels_separate_from_ai_visibility`.

---

## C4 — Gaps — **PASS**

**Assert intent:** `ContentGapReport` evidence-backed; each gap cites page/query evidence; deterministic prioritize.

### Evidence

- Every gap in independent probe had non-empty `evidence[]`; sort key `(severity, gap_type, id)` stable across two runs (identical gap id lists).
- `cite_miss` emitted only when visibility observations present; absent without observations.
- Evidence path: `test_c4_evidence_backed_gaps_only`, `test_c_content_gap_categories_deterministic`, `test_d1_cite_miss_only_with_observations`.

---

## C5 — Brief — **PASS**

**Assert intent:** `opt-brief-v1` cites page-intel + gap-report + queryset fingerprints/versions; retain/rewrite/expand/remove/add with reasons.

### Evidence

- `input_citations` include `page_intel_version`, `gap_report_version`, `query_set_version`, `query_set_id`; `scope` pins methodology + versions.
- Edit actions subset of `{retain,rewrite,expand,remove,add}` with reasons/instructions; `brief_id` deterministic.
- Evidence path: `test_c5_versioned_brief_cites_inputs`, `test_e_brief_deterministic_cites_inputs`, `test_g_change_plan_edit_ops`.

---

## C6 — Grounded draft — **PASS**

**Assert intent:** `OptimizedContentDraft` from brief+source; unsupported claims → warnings; refuse ungrounded factual assert; `paid=False` default; Null/skeleton OK in VERIFY.

### Evidence

- Defaults: `resolve_draft_generator()` → `NullDraftGenerator`; `status=skipped_paid_false`; `paid=False`.
- `content_draft=true` → deterministic skeleton; `unsupported_claims` non-empty; banned phrases (`% of users`, `studies show`, `guaranteed citation`) not presented as fact.
- `PaidLLMDraftGenerator(draft_paid=True, api_key=...)` raises `RuntimeError` refusing live calls.
- Job/API defaults: `content_draft=False`, `draft_paid=False`, `content_draft_provider=None`.
- Evidence path: `test_c6_grounded_draft_citations_refuse_ungrounded`, `test_h_skeleton_draft_when_generate_draft`, `test_i_null_draft_default_unsupported_claims`, `test_s_null_default_no_paid`, `test_t_paid_writer_refuses`.

---

## C7 — Determinism / freezes — **PASS**

**Assert intent:** same inputs → same intel/gaps/brief/change-plan; freezes held.

### Evidence

- Dual `run_content_optimization` with identical inputs: equal `content_hash`, gap ids, `queryset_fingerprint`, `brief_id`, `edit_ops`, draft body, change_plan.
- Freeze path diff vs `main@28a0b85`: **empty** for `ssrf.py`, `target_site.py`, `domains.py`, `scoring/health.py`, `visibility/digitalocean_web_search.py`, `queries/select_v2.py`, `queries/evidence.py`.
- Version pins observed: `health-v1`, `domain-match-v1`, `query-set-v3`, `query-quality-v1`, `sha256_seeded_tiebreak_v1`; AI-search methodology `ai-search-vis-v1:...+domain-match-v1` distinct from LLM-mention `llm-mention-v1:...`; provenance normalize unchanged.
- Evidence path: `test_c7_determinism_and_null_draft_ok`, `test_p_deterministic_same_inputs`, `test_x_freezes_held`.

---

## C8 — SSRF — **PASS**

**Assert intent:** new URL fetches use existing SSRF path; no private/metadata bypass.

### Evidence

- `fetch_html_ssrf_safe` calls `assert_safe_public_url` then `fetch_url` (which re-asserts on redirects).
- `resolve_page_html` rejects via `is_obviously_unsafe_url` before live fetch.
- Independent probe: `127.0.0.1`, `169.254.169.254`, `localhost`, `file://`, `[::1]` blocked by `assert_safe_public_url`.
- API TestClient rejects unsafe `source_url` (no live fetch).
- Evidence path: `test_c8_ssrf_held`, `test_u_api_rejects_unsafe_source_url`.

---

## C9 — Paid off — **PASS**

**Assert intent:** content VERIFY/dry-run performs no paid DO inference/retrieval.

### Evidence

- Content package has no DigitalOcean / inference imports or call sites.
- Offline pipeline dry-run (`html=` fixture, `draft_paid=False`) completes with `paid_retrieval=False`, `paid_llm=False`; no network required.
- Live DO test remains skipped; not executed by Verifier.
- Evidence path: `test_c9_paid_do_off`, `test_x2_no_digitalocean_in_content_package`.

---

## C10 — Suite — **PASS**

**Assert intent:** full pytest green + Phase 5 tests; no live external site deps in tests.

### Evidence

- Full: **205 passed, 1 skipped**; Phase 5 module: **42 passed**.
- Phase 5 tests declare fixtures-only / no live web; SSRF cases use loopback/metadata URLs expected to fail closed; offline HTML + `TestClient` only.
- Evidence path: `test_c10_full_suite_and_phase5_tests_present` + independent suite run.

---

## Artifact integrity

| Check | Result |
| --- | --- |
| `VERIFY-PHASE4*` / `VERIFY-PHASE4.1*` overwritten? | **No** — tip/main diff empty for those paths; this docs PR adds/updates only Phase 5 VERIFY pair |
| Binding docs | `CONTENT_OPTIMIZATION_V1.md` + `PHASE5_EVALUATOR_GATES.md` authoritative; short `CONTENT_OPTIMIZATION.md` defers to V1 (no conflict) |
| CoS structure FLAG | `heading_count` stamped `observed` — non-blocking |
| `engineering_claims_trusted_a_priori` | `false` |
| `paid_digitalocean_apis_run` | `false` |
| `product_commit_sha` | `53e5d11f44ce7e4f9a2e0100007930eac9e9deff` |
| `tip` (≠ product_commit_sha) | `bda584f8858a19642bda96e1b256ee13edd24c78` |
