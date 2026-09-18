# Independent verification — Phase 4.1 Query Intelligence corrective

**Date:** 2026-09-18  
**PR under review:** https://github.com/nik-hil/aeo-service/pull/12  
**Verified SHA (MUST):** `303b6d03940891c93864e7c9eea004382e1dfa73`  
**Branch tip verified:** `cursor/phase41-query-intelligence-corrective-d9f1` @ same SHA  
**Base:** `main` @ `dc4abfe23c25d547158fd7bb04186334b5db36b2`  
**Method:** independent code read + full pytest + independent Python probes; Engineering/PR claims not trusted a priori  
**Paid DigitalOcean APIs:** not run  
**Product code changed by Verifier:** none (docs only)

## Overall: **PASS**

Gate table rows are **assert-intent** labels (what is proven). Test function names are evidence paths only, not the gate identity.

| Gate (assert intent) | Result | Blocks merge? |
| --- | --- | --- |
| **C1:** deterministic SHA tie-break only; no PRNG on v2 select path | **PASS** | yes if FAIL |
| **C2:** same snapshot+seed → identical ordered query_id/text/fingerprint | **PASS** | no |
| **C3:** one shared fingerprint preimage; unstable fields excluded; replay matches | **PASS** | yes if FAIL |
| **C4:** different seeds MAY change ordered set; both seeds remain valid (≥8) | **PASS** | no |
| **C5:** observed-only EVD strength — accepts never slip without ≥2 observed classes | **PASS** | yes if FAIL |
| **C6:** query diagnostics ≠ health-v1; seed ≠ site quality; WEIGHTS unchanged | **PASS** | yes if FAIL |
| **C7:** intent/topic budgets hold; quality gate not seed-bypassed; Hashnode + SaaS fixtures | **PASS** | no |
| **C8:** freezes intact; discovery_only/dry-run zero paid DO / no httpx | **PASS** | yes if FAIL |

**Merge recommendation:** **PASS** — blocking intents C1/C3/C5/C6/C8 all PASS; C2/C4/C7 PASS.

**`different_seed_changed_fixture_set`:** **true**  
(blog and saas fixtures both changed ordered ids + fingerprint for seed 42 vs 99; both remain ≥8 selected)

**Pytest (independent):** `142 passed, 1 skipped, 0 failed`  
**Phase41 file:** `20 passed` (`tests/unit/test_query_discovery_phase41.py`)  
**Skipped:** `tests/unit/test_digitalocean_web_search.py::test_live_digitalocean_web_search_optional` (live paid DO; not run)

**Sibling JSON:** `docs/verification/VERIFY-PHASE4.1-CORRECTIVE-2026-09-18.json`

---

## CoS methodology notes (non-blocking)

### Note 1 — Accepts never slip without ≥2 observed (QSQ-EVD)

**Assert intent:** Even if `generate_v2` / the candidate pool includes derived or compatibility-seeded evidence, **no accept and no selected member** may pass without ≥2 distinct `provenance=observed` evidence classes. Derived-only / compatibility-only / one-observed+derived reject paths must still hold.

**Independent probe (SHA `303b6d0`, no paid DO):**

| Fixture | Natural pool | Injected weak (derived-only, compat-only, 1-obs+derived) | Injected accepted | Accepted obs_min | Selected obs_min | All accepted EVD pass | All selected EVD pass |
| --- | --- | --- | --- | --- | --- | --- | --- |
| blog | 38 | 3 | **0** | **2** | **2** | true | true |
| saas | 41 | 3 | **0** | **2** | **2** | true | true |

- Injected high-confidence weak-provenance candidates were **all rejected** (`injected_rejected_count=3` each fixture).
- Standalone `evaluate_query_v2` on derived+compatibility → `evidence_support=fail`, status `reject`.
- Discovery members: every selected gate `evidence_support=pass` with `observed_evidence_classes` length ≥2.
- Code path: `_dim_evidence` counts only `observed`; discovery orders `gate_candidates_v2` before `select_query_set_v2`.

### Note 2 — Gate rows labeled by assert intent

C1–C8 in this report are identified by **what is proven**, not by unit test names (`test_c5`, `test_c6`, …). Test names may appear under Evidence as paths.

---

## Commands run

```bash
git rev-parse HEAD
# 303b6d03940891c93864e7c9eea004382e1dfa73

python3 -m pip install -e ".[dev]"
pytest -q
# → 142 passed, 1 skipped, 2 warnings in 2.98s

pytest tests/unit/test_query_discovery_phase41.py -v
# → 20 passed

git diff origin/main...HEAD -- \
  src/aeo_mvp/security/ssrf.py \
  src/aeo_mvp/target_site.py \
  src/aeo_mvp/domains.py \
  src/aeo_mvp/scoring/health.py \
  src/aeo_mvp/visibility/digitalocean_web_search.py
# → empty (DIFF_BYTES=0)

rg -n 'random|Random|shuffle' src/aeo_mvp/queries/select_v2.py
# → only docstring prohibition; no import/call

# Independent probes: same-seed replay; seed 42 vs 99; QSQ-EVD accept/select + inject
```

---

## C1 — deterministic SHA tie-break only; no PRNG on v2 select path — **PASS**

**Assert intent:** `selection_seed_method == sha256_seeded_tiebreak_v1`; seed applies only on ties via `sha256(f"{effective_seed}|{query_id}").hexdigest()`; v2 select path has no `random.Random` / shuffle.

### Evidence

- `SELECTION_SEED_METHOD == "sha256_seeded_tiebreak_v1"` in `src/aeo_mvp/queries/select_v2.py`.
- Probe: `seeded_tiebreak_key(42, "q_abc") == hashlib.sha256(b"42|q_abc").hexdigest()`.
- `rg` on `select_v2.py`: no import/call of `random` / `Random` / `shuffle` (comment-only).
- Evidence path: `tests/unit/test_query_discovery_phase41.py::test_c1_seed_sha256_tiebreak_no_prng` PASSED.
- Legacy `select.py` still uses PRNG — out of v2 path scope.

---

## C2 — same snapshot+seed → identical ordered query_id/text/fingerprint — **PASS**

**Assert intent:** Replay identity under identical understanding + seed.

### Evidence

Blog/saas seed 42 twice: ordered ids, texts, fingerprint, and `content_hash` identical; `replay_discovery_fingerprint` matches.  
Evidence paths: `test_c_selection_deterministic_same_seed`, `test_d_same_seed_identical_different_may_differ`.

---

## C3 — one shared fingerprint preimage; unstable fields excluded; replay matches — **PASS**

**Assert intent:** Selection and replay share one preimage; members are stable fields only; audit includes `selection_seed_method`; no `frozen_at`/UUIDs/unstable evidence ids.

### Evidence

- Builders: `canonical_member_payload`, `fingerprint_audit_block`, `canonical_fingerprint_preimage`, `fingerprint_query_set`, `replay_discovery_fingerprint`.
- Probe: `frozen_at="WALL"` absent from preimage; replay equals stored fingerprint.
- Evidence paths: `test_canonical_fingerprint_shared_by_members_and_replay`, `test_c3_fingerprint_excludes_unstable_fields`.

---

## C4 — different seeds MAY change ordered set; both seeds remain valid (≥8) — **PASS**

**Assert intent:** Seed is a real control when ties exist; change is allowed but not required; validity floor ≥8.

### Evidence

| Fixture | selected 42/99 | ordered ids changed | set changed | fingerprint changed |
| --- | --- | --- | --- | --- |
| blog | 20/20 | true | true | true |
| saas | 20/20 | true | true | true |

**`different_seed_changed_fixture_set`: true**

---

## C5 — observed-only EVD strength — accepts never slip without ≥2 observed classes — **PASS**

**Assert intent:** Strongest QSQ-EVD requires ≥2 **observed** classes. Derived/compatibility alone (or one observed + derived) cannot satisfy accept. Selected members inherit the same floor. Pool contamination with weak provenance must not slip into accept/select.

### Evidence

- Code: `quality._dim_evidence` / `observed_evidence_classes` — only `provenance=observed` counts.
- CoS Note 1 probe: blog+saas all accepted/selected `obs_min=2` and `evidence_support=pass`; 3/3 injected weak candidates rejected; derived+compat evaluate → fail.
- Evidence paths: `test_c5_provenance_cannot_satisfy_with_derived_alone`, `test_evidence_provenance_observed_vs_derived`, `test_siteunderstanding_compat_missing_provenance`.
- Discovery order: gate then select — seed cannot bypass EVD.

---

## C6 — query diagnostics ≠ health-v1; seed ≠ site quality; WEIGHTS unchanged — **PASS**

**Assert intent:** Query-set diagnostics are not folded into site health; changing selection seed is not a site-quality delta; health WEIGHTS remain frozen.

### Evidence

- `HEALTH_FORMULA_VERSION == "health-v1"`; WEIGHTS vs `origin/main` empty diff (0.25/0.25/0.20/0.15/0.15).
- `"query"` / `"diagnostic"` absent from WEIGHTS.
- Evidence paths: `test_c6_diagnostics_not_health_and_seed_not_site_quality`, `test_health_v1_frozen_and_no_paid_do`.

---

## C7 — intent/topic budgets hold; quality gate not seed-bypassed; Hashnode + SaaS fixtures — **PASS**

**Assert intent:** Intent maxima and max-per-topic constrain the set; seed does not admit quality rejects; generic SaaS + Hashnode regression hold.

### Evidence

- Blog seed 42: problem_solving=6 (≤6), commercial=0 (≤1); `max_per_topic=4`.
- SaaS observability: SignalWatch/tracing/OTel; no Hashnode/PM hardcode.
- Evidence paths: `test_g_intent_budgets_personal_blog`, `test_h_topic_cap_diversity`, `test_a_generic_generation_saas_observability`, `test_i_hashnode_regression_no_overfit`, `test_f_quality_reject_not_mere_selection`.

---

## C8 — freezes intact; discovery_only/dry-run zero paid DO / no httpx — **PASS**

**Assert intent:** SSRF, domain-match-v1/`TargetSiteIdentity`, health-v1, LLM≠AI-search, DO opt-in default OFF remain unchanged; discovery_only/dry-run never calls paid DO / httpx.

### Evidence

| Freeze path | `git diff origin/main...303b6d0` |
| --- | --- |
| `security/ssrf.py` | empty |
| `target_site.py` | empty |
| `domains.py` | empty |
| `scoring/health.py` | empty |
| `visibility/digitalocean_web_search.py` | empty |

- Defaults: `paid_retrieval_opt_in=False`, `site_understanding_llm=False`.
- Evidence paths: `test_c8_freezes_and_no_paid_do_in_discovery`, `test_health_v1_frozen_and_no_paid_do`.
- Verifier ran no paid DigitalOcean APIs.

---

## content_hash

| Property | Result |
| --- | --- |
| Present on QuerySetV3 / discovery query_set | **yes** |
| Stable under same snapshot+seed | **yes** |
| Changes when fingerprint/seed changes | **yes** (42 vs 99 both fixtures) |

Formula: `sha256(f"{evidence_hash}|{effective_seed}|{version}|{fingerprint}")[:24]`.
