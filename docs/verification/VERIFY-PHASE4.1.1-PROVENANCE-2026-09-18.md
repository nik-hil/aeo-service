# Independent verification — Phase 4.1.1 provenance trust boundary

**Date:** 2026-09-18  
**PR under review:** https://github.com/nik-hil/aeo-service/pull/15  
**Verified product SHA (MUST):** `339ec1567e543dc4491cb2be9a1432ea9710de46`  
**PR tip at re-check:** `677cc4f3091e7d1c6d1333fc5cd0caa3a80ee480` (moved after MUST SHA; tip adds docs + `test_p7` flip only — product provenance code unchanged vs MUST SHA)  
**Base:** `main` @ `e593b4b1be8ecc3d5b47dcdb2ead8ff5a2269518`  
**checklist_version:** `query-set-quality-v1.1.1`  
**Method:** independent code read + full pytest + independent Python probes; Engineering/PR claims not trusted a priori  
**Paid DigitalOcean APIs:** not run  
**Product code changed by Verifier:** none (docs-only PR)

## Overall: **PASS**

Gate table rows are **assert-intent** labels (what is proven). Test function names are evidence paths only, not the gate identity. **ALL gates FAIL → block merge.**

| Gate (assert intent) | Result | Blocks merge? |
| --- | --- | --- |
| **P1:** missing/unknown provenance → compatibility; never silent observed | **PASS** | yes if FAIL |
| **P2:** no implicit observed (ban setdefault/stamp/origin-based promotion) | **PASS** | yes if FAIL |
| **P3:** QSQ-EVD strongest accept requires ≥2 DISTINCT observed classes | **PASS** | yes if FAIL |
| **P4:** generator preserves explicit observed\|derived\|compatibility; missing → compatibility | **PASS** | yes if FAIL |
| **P5:** missing/unknown / foobar → compatibility + EVD fail | **PASS** | yes if FAIL |
| **P6:** arbitrary-site synthetic (SignalWatch/SaaS) same rules; no false observed | **PASS** | yes if FAIL |
| **P7:** freezes held vs main; CORRECTIVE VERIFY untouched | **PASS** | yes if FAIL |
| **P8:** no paid DO / offline; discovery_only; no httpx | **PASS** | yes if FAIL |

**Merge recommendation:** **PASS** — P1–P8 all PASS.

**Pytest @ `339ec15`:** `163 passed, 1 skipped, 0 failed`  
**Pytest @ tip `677cc4f`:** `163 passed, 1 skipped, 0 failed`  
**Phase411 file:** `21 passed` (`tests/unit/test_query_discovery_phase411.py`)  
**Skipped:** `tests/unit/test_digitalocean_web_search.py::test_live_digitalocean_web_search_optional` (live paid DO; not run)

**Sibling JSON:** `docs/verification/VERIFY-PHASE4.1.1-PROVENANCE-2026-09-18.json`  
**Does not overwrite:** `VERIFY-PHASE4.1-CORRECTIVE-2026-09-18.*` (diff vs `main` empty / DIFF_BYTES=0)

---

## Commands run

```bash
git ls-remote origin refs/pull/15/head
# initially 339ec1567e543dc4491cb2be9a1432ea9710de46
# re-check → 677cc4f3091e7d1c6d1333fc5cd0caa3a80ee480

git checkout 339ec1567e543dc4491cb2be9a1432ea9710de46
python3 -m pip install -e ".[dev]"
pytest -q
# → 163 passed, 1 skipped, 2 warnings in 3.31s

pytest tests/unit/test_query_discovery_phase411.py -v
# → 21 passed

git diff e593b4b1be8ecc3d5b47dcdb2ead8ff5a2269518...HEAD -- \
  src/aeo_mvp/security/ssrf.py \
  src/aeo_mvp/target_site.py \
  src/aeo_mvp/domains.py \
  src/aeo_mvp/scoring/health.py \
  src/aeo_mvp/visibility/digitalocean_web_search.py \
  src/aeo_mvp/queries/select_v2.py
# → each DIFF_BYTES=0

rg -n 'setdefault.*observed|provenance.*=.*["'\'']observed' \
  src/aeo_mvp/queries/ src/aeo_mvp/understanding/
# → no setdefault→observed; comparisons only in evidence/generate_v2;
#    builder.py explicit crawl EvidenceRef stamp (not presence promotion)

git diff e593b4b1...HEAD -- docs/verification/VERIFY-PHASE4.1-CORRECTIVE*
# → empty

# Independent Python probes: normalize matrix; stamp presence; QSQ-EVD;
# generate_v2 preserve; missing/foobar EVD; SignalWatch+AcmeSaaS; httpx patch
```

---

## P1 — Normalize: missing/unknown → compatibility; never silent observed — **PASS**

**Assert intent:** Blank/unknown provenance maps to `compatibility` only. Never invent `observed`. Explicit `observed|derived|compatibility` preserved. SiteProfile `heuristic|derived_metric|llm_assist` → `derived`.

### Evidence

- Code: `normalize_provenance` / `EvidenceRecord.from_dict` / `stamp_evidence_dict` in `src/aeo_mvp/queries/evidence.py`.
- Independent matrix (13/13): `None`, `""`, `unknown`, `foobar`, `api_observation`, `bogus`, `synthetic_demo` → `compatibility`; `heuristic|derived_metric|llm_assist` → `derived`; explicit triad preserved.
- `from_dict` missing field → `compatibility`; `stamp_evidence_dict` missing → `compatibility`.
- Evidence path: `tests/unit/test_query_discovery_phase411.py::test_p1_*` / `test_a_*` / `test_b_*` (not gate identity).

---

## P2 — No implicit observed promotion — **PASS**

**Assert intent:** Ban `setdefault`/stamp/origin-based promotion to `observed`. SiteProfile/structured/crawl presence alone ≠ observed.

### Evidence

- `rg setdefault.*observed` / `setdefault("provenance"` across `src/` → **NONE**.
- `setdefault` in `generate_v2.py` / `generate.py` only for `evidence_class` / class buckets — not provenance.
- Independent stamp probe: field `heuristic` → `derived`; field `None` / presence-only dict → `compatibility`; explicit `observed` retained.
- `builder.py` `_ref(..., provenance="observed")` is explicit crawl-extracted `EvidenceRef` construction (hard contract), not later presence→observed promotion. Field/origin on SiteProfile remains separate (`heuristic` default).
- Evidence path: `test_p2_no_implicit_observed_setdefault_or_stamp_to_observed`.

---

## P3 — QSQ-EVD ≥2 DISTINCT `provenance==observed` classes — **PASS**

**Assert intent:** Strongest accept requires ≥2 distinct classes with `provenance==observed`. `derived` / `compatibility` / missing never count. `obs+derived` and two same-class observed must FAIL strongest EVD.

### Evidence

| Case | EVD status | observed_classes | ok |
| --- | --- | --- | --- |
| obs + derived | fail | `[title_h1]` | true |
| two same observed class | fail | `[title_h1]` | true |
| two distinct observed | pass | `[article_body, title_h1]` | true |
| obs + compatibility | fail | `[title_h1]` | true |
| derived + compatibility | fail | `[]` | true |

- Code: `_dim_evidence` / `observed_evidence_classes` in `quality.py` / `evidence.py`.
- Evidence path: `test_p3_*`, `test_c_*`…`test_f_*`.

---

## P4 — Generator preserve explicit; missing → compatibility — **PASS**

**Assert intent:** Explicit `observed|derived|compatibility` retained through generate_v2. Missing fills → `compatibility`. Never lose explicit observed or promote missing → observed.

### Evidence

- Structured path via `_evidence_classes_from_understanding` + `stamp_evidence_dict`:
  - explicit `title_h1`/`observed` retained
  - missing `article_body` → `compatibility`
  - explicit `og_meta`/`derived` retained
  - field `provenance=heuristic` inherit on `jsonld` → `derived` (not observed)
- `generate_candidates_v2`: 30 candidates; explicit observed preserved in candidate `source_evidence`; missing snippet not rewritten to observed.
- Evidence path: `test_p4_*`, `test_g_*`…`test_i_*`.

---

## P5 — Missing/unknown regression → EVD fail — **PASS**

**Assert intent:** No provenance field / `foobar` → normalize to compatibility and strongest EVD fails (does not yield strongest pass).

### Evidence

- Missing field on two classes: normalized `["compatibility","compatibility"]`; `observed_classes=[]`; EVD `fail`.
- `provenance=foobar` on two classes: `observed_classes=[]`; EVD `fail`.
- Evidence path: `test_p5_missing_unknown_regression_evd_fail`.

---

## P6 — Arbitrary-site synthetic (non-Hashnode) same rules — **PASS**

**Assert intent:** SignalWatch/SaaS (and AcmeSaaS) follow same provenance rules; generation works; no false observed; no Hashnode-only assumption.

### Evidence

- SignalWatch SaaS with explicit observed: `31` candidates; `discover_queries(..., discovery_only=True)` → 20 queries; `paid_retrieval_opt_in=false`.
- Weak evidence (missing + derived): EVD `fail`.
- AcmeSaaS structured without provenance: `0` false observed; all items `compatibility|derived`; `31` candidates generated.
- `hashnode_assumption=false`.
- Evidence path: `test_p6_*`, `test_j_*`.

---

## P7 — Freezes held; CORRECTIVE VERIFY untouched — **PASS**

**Assert intent:** health-v1, domain-match-v1, SSRF, llm-mention vs AI-search, diagnostics≠score, `sha256_seeded_tiebreak_v1` untouched vs main. Phase 4.1 CORRECTIVE VERIFY files unchanged in product PR diff.

### Evidence

| Path | DIFF_BYTES vs `e593b4b` |
| --- | ---: |
| `src/aeo_mvp/security/ssrf.py` | 0 |
| `src/aeo_mvp/target_site.py` | 0 |
| `src/aeo_mvp/domains.py` | 0 |
| `src/aeo_mvp/scoring/health.py` | 0 |
| `src/aeo_mvp/visibility/digitalocean_web_search.py` | 0 |
| `src/aeo_mvp/queries/select_v2.py` | 0 |

- `SELECTION_SEED_METHOD == "sha256_seeded_tiebreak_v1"` unchanged; no `random`/`shuffle` on v2 select path.
- `QUALITY_VERSION = "query-quality-v1"`; docstring: diagnostics never folded into health-v1; `WEIGHTS` in health untouched.
- Visibility metrics still pin `llm-mention-v1` / `ai-search-vis-v1` + `domain-match-v1`.
- `git diff ... VERIFY-PHASE4.1-CORRECTIVE*` → empty (DIFF_BYTES=0).
- Tip `677cc4f` vs MUST SHA: product code unchanged; only VERIFY docs + `test_p7` assertion flip.
- Evidence path: `test_p7_freezes_held_no_query_set_v4`.

---

## P8 — No paid DO; offline; no httpx — **PASS**

**Assert intent:** Verification offline; no `web_search` / paid DigitalOcean calls. `discovery_only` keeps paid false.

### Evidence

- `discover_queries(..., discovery_only=True)` with `httpx.Client` / `AsyncClient` patched to raise: `httpx_calls=0`.
- Result flags: `discovery_only=true`, `paid_retrieval_opt_in=false`, `paid_retrieval_ready=false`.
- Live optional DO test skipped (not run).
- `paid_digitalocean_apis_run=false` for this verification.
- Evidence path: `test_p8_no_paid_digitalocean_in_discovery_dry_run`.

---

## Notes

1. **engineering_claims_trusted_a_priori:** `false` — all gates re-probed independently at MUST SHA `339ec15`.
2. Tip movement to `677cc4f` recorded; product provenance trust-boundary code identical to MUST SHA (docs + test assertion only).
3. This docs PR targets `main` and records `verified_sha` so product PR #15 need not be merged first (same pattern as prior VERIFY docs PRs).
