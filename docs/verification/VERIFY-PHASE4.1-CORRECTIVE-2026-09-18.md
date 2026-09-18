# Independent verification — Phase 4.1 Query Intelligence corrective

**Date:** 2026-09-18  
**PR under review:** https://github.com/nik-hil/aeo-service/pull/12  
**Verified SHA:** `303b6d03940891c93864e7c9eea004382e1dfa73` (`cursor/phase41-query-intelligence-corrective-d9f1`)  
**Base:** `main` @ `dc4abfe23c25d547158fd7bb04186334b5db36b2`  
**Method:** independent read of code + full pytest + offline probes; Engineering claims not trusted a priori  
**Paid DigitalOcean APIs:** **no**

## Overall: **PASS**

| Gate | Result |
| --- | --- |
| C1 Same-seed replay + fingerprint; `sha256_seeded_tiebreak_v1` (no PRNG) | **PASS** |
| C2 Different-seed validity (change not required) | **PASS** |
| C3 Canonical fingerprint / content hash | **PASS** |
| C4 Intent / topic caps | **PASS** |
| C5 Quality gates seed-immune | **PASS** |
| C6 Evidence provenance observed\|derived\|compatibility; shim-only cannot accept | **PASS** |
| C7 Hashnode + synthetic site; no hostname special-case | **PASS** |
| C8 No paid DO | **PASS** |

**Pytest (independent):** `142 passed, 1 skipped, 0 failed` (143 collected)  
**Skipped:** `tests/unit/test_digitalocean_web_search.py::test_live_digitalocean_web_search_optional` (live paid DO; gated)  
**Phase 4.1 suite:** `tests/unit/test_query_discovery_phase41.py` → 20 passed  

**Sibling JSON:** `docs/verification/VERIFY-PHASE4.1-CORRECTIVE-2026-09-18.json`

**Paid DO:** no.

---

## Commands run

```bash
git rev-parse HEAD
# 303b6d03940891c93864e7c9eea004382e1dfa73

python3 -m pip install -e ".[dev]"
python3 -m pytest tests/ -v --tb=line
# → 142 passed, 1 skipped, 2 warnings in ~3.3s

python3 -m pytest tests/unit/test_query_discovery_phase41.py -v --tb=line
# → 20 passed

# Freeze paths vs main (empty diffs):
git diff origin/main...HEAD -- \
  src/aeo_mvp/security/ssrf.py \
  src/aeo_mvp/target_site.py \
  src/aeo_mvp/domains.py \
  src/aeo_mvp/scoring/health.py \
  src/aeo_mvp/visibility/digitalocean_web_search.py
# → empty (0 lines each)
```

Offline gate probes (no network / no DO key) re-ran C1–C8 against production modules.

**Live keys present:** `DO_MODEL_ACCESS_KEY=false`, `OPENAI_API_KEY=false`, `PERPLEXITY_API_KEY=false`, `AEO_PAID_RETRIEVAL_OPT_IN=false`.

---

## Seed method hard check — **PASS** (FAIL would fail overall)

Architect binding: `selection_seed_method=sha256_seeded_tiebreak_v1` =
`sha256(f"{effective_seed}|{query_id}").hexdigest()`.

| Check | Evidence |
| --- | --- |
| Constant | `SELECTION_SEED_METHOD == "sha256_seeded_tiebreak_v1"` in `select_v2.py` |
| Formula | `seeded_tiebreak_key(42,"q_abc")` == `c47104dcec2c011b7cf17f83420f31240c2a11aaf81136ad2aef9bbae3289556` |
| No `random` import / `Random` / `shuffle` | AST walk of `select_v2.py` clean |
| MMR uses SHA tie-break | `_mmr_pick` calls `seeded_tiebreak_key`; no `ord()` path |
| Primary path seed-independent | budgets → coverage → MMR score; seed only on `math.isclose` ties |

---

## C1 — Same-seed replay identical ordered set + fingerprint — **PASS**

### Evidence

- Fixture: personal_tech_blog understanding; `selection_seed=42`; `frozen_at=2026-09-18T00:00:00Z` twice.
- Ordered query ids identical (20 members).
- Ordered texts identical.
- Fingerprint identical: `c40aa380a12bc1cbc6a4bba521a0e2c5f4460453087336d3d78379488c86908d`
- `replay_discovery_fingerprint(a) == a.fingerprint == replay_discovery_fingerprint(b)`
- Persisted `selection_seed_method=sha256_seeded_tiebreak_v1`
- Seed method hard check PASS (above)

---

## C2 — Different-seed validity — **PASS**

### Evidence

- Synthetic SaaS observability fixture; seeds 42 vs 99; both `selected_count=20`, both fingerprints non-empty.
- Tie-break keys differ by seed for same `query_id`.
- **Fixture set actually changed:** **yes** (ordered ids and fingerprints differ).
  - seed 42 fingerprint: `d4dab5d034ce3167fa5247f8974e985863779c62f48b6a76acc1b2037402625e`
  - seed 99 fingerprint: `a7529225b5827f1f98599624792d3ffc66c90abda566ed58416e6f794d291666`
- Change is **not required** for PASS; reported for Evaluator transparency.

---

## C3 — Canonical fingerprint / content hash — **PASS**

### Evidence

- ONE shared preimage via `fingerprint_query_set` / `canonical_fingerprint_preimage` / `replay_discovery_fingerprint`.
- Member fields: `query_id, text, intent, topic, entity` only.
- Audit includes `selection_seed_method`, versions, `effective_seed`, `top_k`, `dedup_method`, `mmr_lambda`.
- `frozen_at` excluded from audit and preimage (ISO wall clock not in preimage JSON).
- Members-only digest ≠ full fingerprint (audit tags material).
- `content_hash` present: `e1aefd1528626b8e561c580d`
- Fingerprint from recomputed preimage matches discovery fingerprint.

---

## C4 — Intent / topic caps — **PASS**

### Evidence

- Blog seed=42 intent breakdown: informational 5, problem_solving 6, recommendation 4, comparison 3, navigational 2; commercial ≤ 1; PS ≤ 6 hard max.
- SaaS seed=7: `max_per_topic=4`; topic_breakdown max = 3 ≤ cap.
- `intent_budget_id=intent-budget-v1`, `mmr_lambda=0.65`.

---

## C5 — Quality gates seed-immune — **PASS**

### Evidence

- `HEALTH_FORMULA_VERSION=health-v1`; WEIGHTS unchanged (`technical/content/entity/structured_data/answerability`).
- Seed / query / diagnostic keys absent from WEIGHTS.
- Title-wrap garbage still `reject` via `evaluate_query_v2` independent of selection seed.
- Genre policy (`quality_policy.py`) forbids commercial templates on personal_tech_blog.
- Diagnostics remain query-set quality (`query-quality-v1`), not folded into health-v1.

---

## C6 — Evidence provenance; shim-only cannot accept — **PASS**

### Evidence

- Enum: `observed | derived | compatibility` (`evidence.py`).
- Strongest QSQ-EVD: only `provenance=observed` classes count (≥2).
- Probe matrix:
  - two observed → evidence_support **pass**
  - one observed + one derived → **fail**
  - derived-only → **fail**
  - compatibility-only → **fail**
  - missing provenance (shim / legacy) → treated as compatibility → **fail** (cannot accept)

---

## C7 — Hashnode + synthetic site; no hostname special-case — **PASS**

### Evidence

- Synthetic SignalWatch SaaS: 41 candidates; contains SignalWatch/tracing topics; no AI-agent pack phrases; no `hashnode` string in generated text.
- Hashnode offline fixtures (`nik-hil.hashnode.dev`): discovery_only → 14 selected; method `query-discovery-v2` (no hostname in method); no PM overfit; no `"how do i build an ai agent with tool calling?"` pack phrase; `selection_seed_method=sha256_seeded_tiebreak_v1`; paid off.
- `generate_v2.py`: no `hashnode.dev` / hostname gate branches (docstring negative only).

---

## C8 — No paid DO — **PASS**

### Evidence

- Paid DigitalOcean APIs **not run**.
- `discovery_only=True` + `paid_retrieval_opt_in=True` → result `paid_retrieval_opt_in=False`, `paid_retrieval_ready=False`; `httpx.Client` / `AsyncClient` not called.
- Live DO optional test skipped (not executed).
- No `DO_MODEL_ACCESS_KEY` in environment.

---

## Freezes — **PASS**

| Freeze surface | Evidence |
| --- | --- |
| health-v1 | 0-line diff vs main; VERSION + WEIGHTS unchanged |
| domain-match-v1 | 0-line diff `target_site.py`/`domains.py`; Hashnode identity `match_rule_version=domain-match-v1`, `match_scope=hostname`, `registrable_domain=hashnode.dev`, `multi_tenant_host=true` |
| SSRF | 0-line diff `ssrf.py`; `test_ssrf.py` green in full suite |
| LLM-mention vs AI-search | DO caps: `retrieval_enabled=True`, `experiment_kinds=['ai_search_visibility']`, `measures_consumer_ui=False`; OpenAI-compatible / Demo = `llm_mention` only |
| DO opt-in | provider file 0-line diff; discovery_only forces paid false |

---

## Pytest inventory (independent)

| Suite | Result |
| --- | --- |
| Full `tests/` | 142 passed, 1 skipped, 0 failed (143 collected) |
| Phase 4.1 `test_query_discovery_phase41.py` | 20 passed |

**Engineering claim cross-check:** PR claimed 142 passed, 1 skipped @ `303b6d0` — **matches** independent run.

---

## Diff scope note

Phase 4.1 touches discovery/select/quality/evidence/quality_policy + tests + methodology docs. Freeze paths listed above are untouched relative to `main` @ `dc4abfe`. No product-code changes in this verifier commit (docs only).
