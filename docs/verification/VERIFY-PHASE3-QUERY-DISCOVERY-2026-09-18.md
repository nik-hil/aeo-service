# Independent verification — Phase 3 SiteProfile + query-discovery-v1

**Date:** 2026-09-18  
**PR under review:** https://github.com/nik-hil/aeo-service/pull/4  
**Verified SHA:** `3874f644f202c71c105d62ca62bdcf242354d510` (`cursor/phase3-query-discovery-ff83`)  
**Base:** `main` @ `c67124ec196ca9a6299c09da54992c7e5ea90357`  
**Verifier branch:** `cursor/verify-phase3-query-discovery-2704` (docs/verification only)  
**Method:** read code + run tests; Engineering claims (107/1; Hashnode ≠ `project_management`) not trusted a priori

## Overall: **PASS**

| Gate | Result |
| --- | --- |
| A Site classification | **PASS** |
| B Query discovery integrity | **PASS** |
| C Deterministic selection | **PASS** |
| D Cost / offline | **PASS** |
| E Regression FREEZE | **PASS** |
| F Quality gate | **PASS** |

**Pytest (independent):** `107 passed, 1 skipped, 0 failed` (108 collected)  
**Skipped:** `test_live_digitalocean_web_search_optional` (live paid DO; gated)

**Sibling JSON:** `docs/verification/VERIFY-PHASE3-QUERY-DISCOVERY-2026-09-18.json`

---

## Commands run

```bash
git rev-parse HEAD
# 3874f644f202c71c105d62ca62bdcf242354d510

git checkout -b cursor/verify-phase3-query-discovery-2704
python3 -m pip install -e ".[dev]"

# Phase 3 targeted
python3 -m pytest tests/unit/test_site_profile.py \
  tests/unit/test_query_discovery_v2.py -v --tb=short
# → 14 passed

# FREEZE suites
python3 -m pytest tests/unit/test_target_site.py \
  tests/unit/test_ssrf.py tests/unit/test_scoring.py -v --tb=short
# → 50 passed
python3 -c "from aeo_mvp.scoring.health import WEIGHTS; print(WEIGHTS)"
# → {'technical': 0.25, 'content': 0.25, 'entity': 0.2,
#    'structured_data': 0.15, 'answerability': 0.15}

# Full suite
python3 -m pytest tests/ -v --tb=line
# → 107 passed, 1 skipped, 2 warnings

# Manual Hashnode fixtures + seed reproducibility (see logs below)
python3 <<'EOF'
# build_structured_profile + discover_queries(selection_seed=42) x2
EOF
```

**Diff scope vs `c67124e`:** 32 files, +4488 / −326 — SiteProfile builder, query generate/normalize/gate/select, fixtures, tests, ADRs.  
**Freeze files untouched vs base:** `src/aeo_mvp/scoring/health.py`, `security/ssrf.py`, `target_site.py`, `domains.py` (empty `git diff c67124e...3874f64` on those paths).

---

## Gate A — Site classification — **PASS**

### A1 Evidence-backed SiteProfile — PASS

`StructuredSiteProfile` / `SiteProfileField` wrap assertive fields with `value`, `confidence`, `provenance`, `evidence[]` (`evidence_id`, `url`, `snippet`, `evidence_class`) — `src/aeo_mvp/understanding/profile.py`.

Manual Hashnode fixture run (`tests/fixtures/hashnode/`):

| Field | value | conf | provenance | sample evidence |
| --- | --- | --- | --- | --- |
| `site_genre` | `personal_tech_blog` | 0.40 | heuristic | jsonld Person @ article URL, snippet `Nikhil Ikhar` |
| `industry_category` | `ai_ml` | 0.40 | heuristic | title_h1 / jsonld AI-agent titles (not omitted) |
| `primary_topics` | agent/tool topics | 0.38 | heuristic | title_h1 + article_body H2s |
| `org_name` | `Nikhil Ikhar` | 0.36 | heuristic | jsonld Person |

Heuristic cap `HEURISTIC_CONFIDENCE_CAP = 0.40` enforced (`test_heuristic_confidence_cap_and_llm_merge_guard`).

### A2 Hashnode not primarily `project_management` — PASS

- Manual: `industry_category_guess == "ai_ml"`, `assertive_industry() == "ai_ml"`, `!= "project_management"`.
- Genre: `personal_tech_blog`.
- Tags not in products: `products_services == []`.
- Fixture aside contains chrome “Roadmap…”; weak-only PM tokens never assert (`_industry_votes` + genre gate in `builder.py`).
- Tests: `test_hashnode_not_project_management`, `test_hashnode_structured_profile_evidence`, `test_unrelated_category_rejected_without_evidence` — all PASSED.
- Legitimate PM still classifies with strong evidence: `test_acme_still_gets_pm_with_strong_evidence` PASSED.

### A3 Category/industry provenance + confidence; no unexplained hardcodes — PASS

- Industry asserted only after strong-vote thresholds (≥3, lead ≥2, ≥2 non-chrome evidence classes) or genre-gate remapping to `ai_ml` with topic evidence; otherwise omitted (`test_insufficient_evidence_omits_industry`).
- Pattern tables `INDUSTRY_STRONG` / `INDUSTRY_WEAK` are documented heuristics with evidence refs — not silent hardcodes of Hashnode→industry.
- Methodology: `docs/methodology/QUERY_DISCOVERY.md`, ADR-024.

**Note (non-failing):** one industry evidence snippet still shows chrome nav text under `article_body` class (“…Latest articles Roadmap…”). Classification outcome remains correct (`ai_ml`, not PM); chrome vote cap + weak-token rules prevent the prior regression.

---

## Gate B — Query discovery integrity — **PASS**

### B4 Evidence-traced queries — PASS

- Candidates carry `evidence_classes`, `source_evidence`, `rationale`, `confidence` (`generate.py`).
- Manual: 40/40 candidates had evidence classes + rationale; selected 20/20 had `source_evidence` or `rationale`.
- `test_evidence_provenance_on_queries` PASSED.
- No fabricated PM facts: 0 candidates / 0 selected contained “project management” on Hashnode fixtures.

### B5 Confidence + provenance — PASS

- SiteProfile fields as above; queries score via confidence; discovery `provenance="derived_metric"`, method `query-discovery-v1`.

### B6 Intent coverage documented/tested — PASS

- Documented in `docs/methodology/QUERY_DISCOVERY.md` (intent mix for personal_tech_blog).
- `test_intent_assignment_personal_blog` PASSED (informational + problem_solving; forbids cost/alternatives/PM templates).
- Manual selected intent_breakdown (seed=42):  
  `informational:5, problem_solving:5, recommendation:5, comparison:4, navigational:1`.

### B7 Dedup proven by tests — PASS

- `test_normalize_and_near_dup`, `test_legacy_discover_and_dedupe_still_work` PASSED.
- Manual: `dedupe_by_text` on near-dup pair → 3→2; `is_near_duplicate("What is AI Agent?", "what is ai agent?")` True; NFKC/whitespace normalize works.

---

## Gate C — Deterministic selection — **PASS**

### C8 Fixed seed reproducibility — PASS

- `test_deterministic_selection_seed_reproducible` PASSED.
- Manual: `discover_queries(..., selection_seed=42)` twice → identical selected text list/order; `query_set_version=query-set-v2`.

### C9 ~20 from 30–50 candidates — PASS

| Metric | Actual (Hashnode fixtures, seed=42) |
| --- | --- |
| `generate_candidates` | **40** (in 30–50) |
| post-dedupe `candidates_count` | **40** |
| accepted / rejected | **40 / 0** |
| selected (`top_n=20`) | **20** |

---

## Gate D — Cost / offline — **PASS**

### D10 No paid API by default in unit/CI — PASS

- `Settings.paid_retrieval_opt_in` default `False` (`AEO_PAID_RETRIEVAL_OPT_IN`).
- Discovery never calls DO/OpenAI; `paid_retrieval_ready` only when opt-in ∧ ready set.
- Env during run: `DO_MODEL_ACCESS_KEY` / `OPENAI_API_KEY` / `PERPLEXITY_API_KEY` unset.
- Manual default: `paid_retrieval_opt_in=False`, `paid_retrieval_ready=False`.

### D11 Unit tests green without live keys; paid skipped/gated — PASS

- Full pytest green with no keys.
- Live DO test skipped: `test_live_digitalocean_web_search_optional`.
- Providers raise without keys: `test_openai_provider_requires_key`, `test_provider_requires_key`, `test_perplexity_raises_without_key`.
- `test_paid_retrieval_requires_opt_in` PASSED.

---

## Gate E — Regression FREEZE — **PASS**

### E12 Full pytest ≥93 — PASS

**Recorded:** `107 passed, 1 skipped, 0 failed` (matches Engineering claim; independently reproduced).

### E13 TargetSiteIdentity Hashnode hostname matrix — PASS

- `test_hashnode_hostname_scope_matrix[...]` (15 parametrized cases) + related identity tests — all PASSED in full suite.
- Diff vs base: `target_site.py` / `domains.py` unchanged.

### E14 health-v1 weights unchanged — PASS

```text
WEIGHTS = {
  technical: 0.25, content: 0.25, entity: 0.20,
  structured_data: 0.15, answerability: 0.15
}
```

- Identical to `c67124e`; `test_health_worked_example` → H=70.0 PASSED.

### E15 SSRF suite green — PASS

- All `tests/unit/test_ssrf.py` cases PASSED (blocked localhost/private/metadata/file/ftp; redirect-to-private rejected).
- `security/ssrf.py` untouched vs base.

---

## Gate F — Quality gate — **PASS**

### F16 Accept/reject reasons — PASS

- `GateDecision` carries `status`, `reasons[]`, per-dimension `pass|fail|warn` (`gate.py`).
- Accept path records `all_dimensions_pass` or warn reasons; reject concatenates `name:status:detail`.

### F17 Rejected candidates retain auditable reason codes — PASS

- `discover_queries` stores `rejected_examples` with full `decision.to_dict()`.
- Synthetic leak query → `status=reject`, reasons include  
  `WEAK_INDUSTRY_LEAK:fail:project_management language without assertive industry evidence`.
- `test_weak_industry_leak_rejected` PASSED.
- Hashnode happy path had 0 rejects (all 40 accepted) — expected; reject path covered by tests + synthetic check.

---

## Top issues / observations

1. **None blocking.** Overall PASS; Eng claims on pytest count and Hashnode≠PM independently confirmed.
2. **Non-blocking:** chrome “Roadmap” text can appear in an `article_body` evidence snippet; weak-token + genre rules still prevent PM misclassification. Worth a follow-up to tighten chrome stripping if evidence hygiene is audited strictly.

---

## Artifact paths

- This report: `docs/verification/VERIFY-PHASE3-QUERY-DISCOVERY-2026-09-18.md`
- Machine-readable: `docs/verification/VERIFY-PHASE3-QUERY-DISCOVERY-2026-09-18.json`
- Command logs (local verify run): `/tmp/verify-phase3/` (`full_pytest.log`, `targeted.log`, `freeze.log`, `manual_hashnode.log`, `gate_reject_dedupe.log`)
