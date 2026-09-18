# Independent verification — Phase 4.1 Query Intelligence corrective

**Date:** 2026-09-18  
**PR under review:** https://github.com/nik-hil/aeo-service/pull/12  
**Verified SHA (MUST):** `303b6d03940891c93864e7c9eea004382e1dfa73`  
**Branch tip verified:** `cursor/phase41-query-intelligence-corrective-d9f1` @ same SHA  
**Base:** `main` @ `dc4abfe23c25d547158fd7bb04186334b5db36b2`  
**Method:** independent code read + full pytest + independent Python probe; Engineering/PR claims not trusted a priori  
**Paid DigitalOcean APIs:** not run  
**Product code changed by Verifier:** none (docs only)

## Overall: **PASS**

| Gate | Result | Blocks merge? |
| --- | --- | --- |
| C1 SHA tie-break; no PRNG on v2 | **PASS** | yes if FAIL |
| C2 same snapshot+seed replay | **PASS** | no |
| C3 one shared fingerprint preimage | **PASS** | yes if FAIL |
| C4 different seeds MAY change set | **PASS** | no |
| C5 evidence provenance (observed) | **PASS** | yes if FAIL |
| C6 diagnostics ≠ health; WEIGHTS frozen | **PASS** | yes if FAIL |
| C7 intent/topic constraints + fixtures | **PASS** | no |
| C8 freezes + zero paid DO in discovery | **PASS** | yes if FAIL |

**Merge recommendation:** **PASS** — C1/C3/C5/C6/C8 all PASS; C2/C4/C7 PASS.

**`different_seed_changed_fixture_set`:** **true**  
(blog and saas fixtures both changed ordered ids + fingerprint for seed 42 vs 99; both remain ≥8 selected)

**Pytest (independent):** `142 passed, 1 skipped, 0 failed`  
**Phase41 file:** `20 passed` (`tests/unit/test_query_discovery_phase41.py`)  
**Skipped:** `tests/unit/test_digitalocean_web_search.py::test_live_digitalocean_web_search_optional` (live paid DO; not run)

**Sibling JSON:** `docs/verification/VERIFY-PHASE4.1-CORRECTIVE-2026-09-18.json`

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
# → only docstring prohibition line 8; no import/call

# Independent probe: same seed twice; seed 42 vs 99 on blog + saas fixtures
# (see C2/C4 evidence below)
```

---

## C1 — `sha256_seeded_tiebreak_v1`; no PRNG — **PASS**

### Evidence

- `SELECTION_SEED_METHOD == "sha256_seeded_tiebreak_v1"` in `src/aeo_mvp/queries/select_v2.py`.
- `seeded_tiebreak_key(effective_seed, query_id)` = `sha256(f"{effective_seed}|{query_id}").hexdigest()`.
- Independent check: `seeded_tiebreak_key(42, "q_abc") == hashlib.sha256(b"42|q_abc").hexdigest()`.
- `rg` on `select_v2.py`: no `import random`, no `Random(`, no `.shuffle(` (comment-only mention).
- AST guard test `test_c1_seed_sha256_tiebreak_no_prng` PASSED.
- Note: legacy `select.py` still uses `random.Random` — out of scope; v2 path is `select_query_set_v2`.

---

## C2 — same snapshot+seed → identical ordered set — **PASS**

### Evidence (independent probe)

Blog fixture, seed 42, twice:

| Field | Run A | Run B | Match |
| --- | --- | --- | --- |
| ordered query_ids | 20 ids | same | yes |
| ordered texts | same | same | yes |
| fingerprint | `c40aa380…86908d` | same | yes |
| content_hash | `e1aefd1528626b8e561c580d` | same | yes |
| replay_discovery_fingerprint | equals fingerprint | — | yes |

SaaS fixture: same-seed identical (`fingerprint` `d4dab5d0…7402625e`, `content_hash` `9c4fd14afe2ea6c8f3d24ef2`).

Unit: `test_c_selection_deterministic_same_seed`, `test_d_same_seed_identical_different_may_differ` PASSED.

---

## C3 — ONE shared fingerprint preimage — **PASS**

### Evidence

- Shared builders: `canonical_member_payload`, `fingerprint_audit_block`, `canonical_fingerprint_preimage`, `fingerprint_query_set`, `replay_discovery_fingerprint`.
- Member fields only: `query_id, text, intent, topic, entity` — no `frozen_at` / UUIDs / unstable evidence ids.
- `fingerprint_audit` includes `selection_seed_method` (plus versions, `effective_seed`, `top_k`, `dedup_method`, `mmr_lambda`, …).
- Probe: `frozen_at="WALL"` not present in preimage JSON; `replay_discovery_fingerprint(r) == r.fingerprint`.
- Members-only digest ≠ full preimage (intentional).
- Tests: `test_canonical_fingerprint_shared_by_members_and_replay`, `test_c3_fingerprint_excludes_unstable_fields` PASSED.

---

## C4 — different seeds MAY change ordered set — **PASS**

Requirement: do **not** require change; both seeds valid (≥8). Report whether fixtures actually changed.

### Evidence (independent probe)

| Fixture | seed 42 count | seed 99 count | ordered ids changed | set ids changed | fingerprint changed |
| --- | --- | --- | --- | --- | --- |
| blog | 20 | 20 | **true** | **true** | **true** |
| saas | 20 | 20 | **true** | **true** | **true** |

- Blog fp 42→99: `c40aa380…` → `ac9ea010…`
- SaaS fp 42→99: `d4dab5d0…` → `a7529225…`
- Tie-break keys for same `query_id` differ by seed (expected).

**`different_seed_changed_fixture_set`: true** (both fixtures).

---

## C5 — evidence provenance / QSQ-EVD — **PASS**

### Evidence

- `quality._dim_evidence`: only `provenance=observed` classes count; ≥2 required.
- Derived/compatibility alone → `evidence_support` fail (cannot satisfy strongest QSQ-EVD).
- Missing provenance → compatibility (fail for strongest gate).
- Tests: `test_c5_provenance_cannot_satisfy_with_derived_alone`, `test_evidence_provenance_observed_vs_derived`, `test_siteunderstanding_compat_missing_provenance` PASSED.
- Discovery order: `gate_candidates_v2` then `select_query_set_v2` — seed cannot bypass quality gate.

---

## C6 — diagnostics ≠ health-v1; WEIGHTS unchanged — **PASS**

### Evidence

- `HEALTH_FORMULA_VERSION == "health-v1"`.
- `WEIGHTS` unchanged vs `origin/main` (0-byte freeze diff on `scoring/health.py`): technical 0.25, content 0.25, entity 0.20, structured_data 0.15, answerability 0.15.
- Seed is selection control only — not a health input (`"query"` / `"diagnostic"` absent from WEIGHTS).
- Genre policy in `quality_policy.py`; diagnostics are query-set quality, not site grade.
- Test `test_c6_diagnostics_not_health_and_seed_not_site_quality` PASSED.

---

## C7 — intent/topic constraints; Hashnode + SaaS fixtures — **PASS**

### Evidence

- Blog intent budgets (seed 42): problem_solving ≤6 (observed 6), commercial ≤1 (observed 0).
- Topic cap: `max_per_topic=4`; blog/saas topic breakdown max ≤4.
- SaaS observability synthetic site generates SignalWatch/tracing/OTel queries; no Hashnode/PM hardcode.
- Hashnode fixture regression (`test_i_hashnode_regression_no_overfit`) PASSED; `discovery_only` paid off.
- Quality rejects (title-wrap / commercial leak) still reject — seed does not bypass.

---

## C8 — freezes intact; discovery_only / dry-run zero paid DO — **PASS**

### Evidence

| Freeze path | `git diff origin/main...HEAD` |
| --- | --- |
| `src/aeo_mvp/security/ssrf.py` | empty |
| `src/aeo_mvp/target_site.py` (`domain-match-v1` / `TargetSiteIdentity`) | empty |
| `src/aeo_mvp/domains.py` | empty |
| `src/aeo_mvp/scoring/health.py` | empty |
| `src/aeo_mvp/visibility/digitalocean_web_search.py` | empty |

- Config defaults: `AEO_PAID_RETRIEVAL_OPT_IN=False`, `AEO_SITE_UNDERSTANDING_LLM=False`.
- LLM assist ≠ AI-search visibility provider (separate modules; LLM default off).
- `discovery_only` / dry-run forces `paid_retrieval_opt_in=False`; httpx Client/AsyncClient not called under patch (tests PASSED).
- Verifier ran **no** paid DigitalOcean APIs.

---

## content_hash

| Property | Result |
| --- | --- |
| Present on QuerySetV3 / discovery query_set | **yes** |
| Stable under same snapshot+seed | **yes** (blog/saas probe) |
| Changes when fingerprint/seed changes | **yes** (42 vs 99 differed on both fixtures) |

Formula (code): `sha256(f"{evidence_hash}|{effective_seed}|{version}|{fingerprint}")[:24]`.
