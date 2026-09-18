# Independent verification — Phase 4.1.1 Evidence provenance trust boundary

**Date:** 2026-09-18  
**PR under review:** https://github.com/nik-hil/aeo-service/pull/15  
**Verified SHA (MUST):** `339ec1567e543dc4491cb2be9a1432ea9710de46`  
**Branch tip verified:** `cursor/phase411-provenance-boundary-ff49` @ same SHA  
**Base:** `main` @ `e593b4b1be8ecc3d5b47dcdb2ead8ff5a2269518`  
**Binding:** `docs/architecture/PHASE4_1_1_PROVENANCE_LOCK.md`  
**Methodology:** `query-set-quality-v1.1.1` (frozen code gate remains `query-quality-v1` / `query-set-v3`)  
**Method:** independent code read + full pytest + independent Python probes; Engineering/PR claims not trusted a priori  
**Paid DigitalOcean APIs:** not run  
**Product code changed by Verifier:** none (docs only; `test_p7` assertion flipped to require this VERIFY artifact)

## Overall: **PASS**

Gate table rows are **assert-intent** labels (what is proven). Test function names are evidence paths only, not the gate identity.

| Gate (assert intent) | Result | Blocks merge? |
| --- | --- | --- |
| **P1:** missing/unknown → compatibility (never silent observed) | **PASS** | yes if FAIL |
| **P2:** no implicit observed promotion (ban setdefault/stamp-to-observed) | **PASS** | yes if FAIL |
| **P3:** QSQ-EVD ≥2 distinct observed only | **PASS** | yes if FAIL |
| **P4:** generator preserves explicit; missing → compatibility | **PASS** | yes if FAIL |
| **P5:** missing/unknown EVD fail regression | **PASS** | yes if FAIL |
| **P6:** arbitrary-site synthetic same provenance rules | **PASS** | no |
| **P7:** freezes held (ssrf, target_site, domains, health, DO provider); no query-set-v4; 4.1 CORRECTIVE untouched | **PASS** | no |
| **P8:** no paid DO in discovery/dry-run | **PASS** | yes if FAIL |

**Merge recommendation:** **PASS** — blocking intents P1/P2/P3/P4/P5/P8 all PASS; P6/P7 PASS.

**Pytest (independent):** `163 passed, 1 skipped, 0 failed`  
**Phase411 file:** `21 passed` (`tests/unit/test_query_discovery_phase411.py`)  
**Skipped:** `tests/unit/test_digitalocean_web_search.py::test_live_digitalocean_web_search_optional` (live paid DO; not run)

**Sibling JSON:** `docs/verification/VERIFY-PHASE4.1.1-PROVENANCE-2026-09-18.json`  
**Does not overwrite:** `VERIFY-PHASE4.1-CORRECTIVE-2026-09-18.*` (diff vs `main` empty)

---

## Commands run

```bash
git rev-parse HEAD
# 339ec1567e543dc4491cb2be9a1432ea9710de46

python3 -m pip install -e ".[dev]"
pytest -q
# → 163 passed, 1 skipped, 2 warnings in 3.18s

pytest tests/unit/test_query_discovery_phase411.py -v
# → 21 passed

git diff origin/main...HEAD -- \
  src/aeo_mvp/security/ssrf.py \
  src/aeo_mvp/target_site.py \
  src/aeo_mvp/domains.py \
  src/aeo_mvp/scoring/health.py \
  src/aeo_mvp/visibility/digitalocean_web_search.py
# → empty (DIFF_BYTES=0)

git diff origin/main...HEAD -- \
  docs/verification/VERIFY-PHASE4.1-CORRECTIVE-2026-09-18.md \
  docs/verification/VERIFY-PHASE4.1-CORRECTIVE-2026-09-18.json
# → empty

# Independent probes: normalize_provenance matrix; adapter banned-pattern scan;
# QSQ-EVD pass/fail matrix; generate_v2 preserve/fill; missing/unknown EVD fail;
# CedarLedger arbitrary site; freeze + version pins; httpx mock under discovery_only
```

---

## P1 — missing/unknown → compatibility (never silent observed) — **PASS**

**Assert intent:** Missing, empty, and unknown provenance strings map to `compatibility` only; never invent `observed`. Explicit `observed|derived|compatibility` preserved. SiteProfile `heuristic|derived_metric|llm_assist` → `derived`. Methodology id is `query-set-quality-v1.1.1`.

### Evidence

- Code: `normalize_provenance` / `EvidenceRecord.from_dict` / `stamp_evidence_dict` in `src/aeo_mvp/queries/evidence.py`.
- Independent probe: `None`, `""`, `unknown`, `api_observation`, `synthetic_demo`, `estimate`, `bogus` → `compatibility`; `heuristic` → `derived`; missing dict → stamp `compatibility` (14/14 checks).
- Evidence path: `tests/unit/test_query_discovery_phase411.py::test_p1_normalize_missing_unknown_to_compatibility_never_observed` PASSED.

---

## P2 — no implicit observed promotion — **PASS**

**Assert intent:** Query adapters must not `setdefault(..., "observed")` or assign `["provenance"]="observed"` when provenance is missing; must route through `normalize_provenance` / `stamp_evidence_dict`.

### Evidence

- Independent `rg` + read of `generate_v2.py`, `generate.py`, `evidence.py`: no banned patterns; no missing→observed branch.
- Crawl `EvidenceRef` may stamp `observed` only at construction (`builder._ref` hard contract) — out of adapter scope; field origin ≠ evidence provenance.
- Evidence path: `tests/unit/test_query_discovery_phase411.py::test_p2_no_implicit_observed_setdefault_or_stamp_to_observed` PASSED.

---

## P3 — QSQ-EVD ≥2 distinct observed only — **PASS**

**Assert intent:** Strongest EVD requires ≥2 **distinct** classes with `provenance=observed`. Derived, compatibility, and same-class duplicates do not satisfy.

### Evidence

| Evidence | EVD | observed class count |
| --- | --- | --- |
| two distinct observed | **pass** | 2 |
| observed + derived | fail | 1 |
| observed + compatibility | fail | 1 |
| derived-only | fail | 0 |
| two same-class observed | fail | 1 |

- Code: `quality._dim_evidence` / `observed_evidence_classes`.
- Evidence path: `tests/unit/test_query_discovery_phase411.py::test_p3_qsq_evd_requires_two_distinct_observed_only` PASSED.

---

## P4 — generator preserves explicit; missing → compatibility — **PASS**

**Assert intent:** `generate_v2` / `_evidence_classes_from_understanding` preserves explicit `observed|derived|compatibility`; fills missing → `compatibility` (never manufactured observed).

### Evidence

Independent AcmeGarden fixture:

| snippet | provenance |
| --- | --- |
| Tomato pruning (explicit observed) | observed |
| soil (explicit derived) | derived |
| clay (missing) | compatibility |
| AcmeGarden (explicit compatibility) | compatibility |

- 18 candidates generated; all evidence provenances in `{observed, derived, compatibility}`; clay remains compatibility.
- Evidence path: `tests/unit/test_query_discovery_phase411.py::test_p4_generator_preserves_explicit_fills_missing_compatibility` PASSED.

---

## P5 — missing/unknown EVD fail regression — **PASS**

**Assert intent:** Candidates whose evidence is missing or unknown-normalized cannot pass QSQ-EVD; generator path with missing structured provenance still produces candidates for viability but all fail EVD.

### Evidence

- Missing two-class evidence → EVD fail, `observed_evidence_classes` length 0.
- Unknown (`bogus` / `api_observation`) → normalized away from observed → EVD fail.
- Weak structured (no provenance): 18 candidates, all EVD fail, zero observed classes.
- Evidence path: `tests/unit/test_query_discovery_phase411.py::test_p5_missing_unknown_regression_evd_fail` PASSED.

---

## P6 — arbitrary-site synthetic same rules — **PASS**

**Assert intent:** Non-Hashnode synthetic site (CedarLedger) follows the same trust boundary; weak missing → compatibility; discovery with explicit observed selects ≥8 with ≥2 observed classes; no Hashnode overfit.

### Evidence

- Weak CedarLedger missing provenance → `compatibility` for books/schema snippets.
- Discovery seed 11: `selected_count=20`; joined queries contain `cedar`, not `hashnode`; all selected have ≥2 observed classes.
- Evidence path: `tests/unit/test_query_discovery_phase411.py::test_p6_arbitrary_site_synthetic_same_provenance_rules` PASSED.

---

## P7 — freezes held; no query-set-v4; 4.1 CORRECTIVE untouched — **PASS**

**Assert intent:** SSRF, TargetSiteIdentity/domains, health-v1, DO provider freeze paths unchanged vs `main`; versions pinned (`query-quality-v1`, `query-set-v3`, `query-discovery-v2`, `intent-budget-v1`, `sha256_seeded_tiebreak_v1`, methodology `query-set-quality-v1.1.1`); no `query-set-v4`; Phase 4.1 CORRECTIVE VERIFY files unmodified.

### Evidence

| Freeze path | `git diff origin/main...339ec15` |
| --- | --- |
| `security/ssrf.py` | empty |
| `target_site.py` | empty |
| `domains.py` | empty |
| `scoring/health.py` | empty |
| `visibility/digitalocean_web_search.py` | empty |

| Pin | Value |
| --- | --- |
| `QUALITY_VERSION` | `query-quality-v1` |
| `QUERY_SET_QUALITY_METHODOLOGY` | `query-set-quality-v1.1.1` |
| `QUERY_SET_VERSION` | `query-set-v3` (≠ v4) |
| `SELECTION_SEED_METHOD` | `sha256_seeded_tiebreak_v1` |
| `DISCOVERY_METHOD_V2` | `query-discovery-v2` |
| `INTENT_BUDGET_ID` | `intent-budget-v1` |
| `HEALTH_FORMULA_VERSION` | `health-v1` |

- `VERIFY-PHASE4.1-CORRECTIVE-2026-09-18.{md,json}` diff vs `main`: empty.
- Evidence path: `tests/unit/test_query_discovery_phase411.py::test_p7_freezes_held_no_query_set_v4` PASSED (assertion updated post-VERIFY to require this artifact’s presence).

---

## P8 — no paid DO in discovery/dry-run — **PASS**

**Assert intent:** `discovery_only` / dry-run makes zero paid DigitalOcean / `httpx` calls even if `paid_retrieval_opt_in=True` is requested; result flags remain false.

### Evidence

- Independent probe: patched `httpx.Client` / `httpx.AsyncClient` — neither called under `discover_queries(..., discovery_only=True, paid_retrieval_opt_in=True)`.
- Result: `paid_retrieval_opt_in=False`, `paid_retrieval_ready=False`, `method=query-discovery-v2`.
- Verifier ran no paid DigitalOcean APIs.
- Evidence path: `tests/unit/test_query_discovery_phase411.py::test_p8_no_paid_digitalocean_in_discovery_dry_run` PASSED.
