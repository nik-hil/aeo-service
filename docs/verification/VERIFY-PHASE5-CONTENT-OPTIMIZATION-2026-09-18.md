# Independent verification — Phase 5 content optimization (`content-optimization-v1`)

**Date:** 2026-09-18  
**PR under review:** https://github.com/nik-hil/aeo-service/pull/17  
**product_commit_sha (MUST):** `53e5d11f44ce7e4f9a2e0100007930eac9e9deff`  
**Branch tip verified (product):** `cursor/phase5-content-optimization-ae1e` @ same SHA  
**Base:** `main` @ `28a0b8526f3c76c6116565aa2ef08256201976bd`  
**Binding:** `docs/methodology/CONTENT_OPTIMIZATION_V1.md` · `docs/architecture/PHASE5_RECONCILED_CONTRACTS.md`  
**Methodology:** `content-optimization-v1`  
**Method:** independent code read + full pytest + independent Python probes; Engineering/PR claims not trusted a priori  
**Paid DigitalOcean APIs / paid LLM:** not run  
**Product code changed by Verifier:** none (docs-only VERIFY artifacts; may trail product SHA)

## Overall: **PASS**

Gate table rows are **assert-intent** labels (what is proven). Test function names are evidence paths only, not the gate identity.

| Gate (assert intent) | Result | Blocks merge? |
| --- | --- | --- |
| **C1:** Page intel + provenance + hostname scope | **PASS** | yes if FAIL |
| **C2:** generated≠observed; draft never enters observed stores | **PASS** | yes if FAIL |
| **C3:** Coverage from snapshot themes; coverage≠visibility≠health | **PASS** | yes if FAIL (default) |
| **C4:** Evidence-backed gaps; deterministic prioritize | **PASS** | yes if FAIL |
| **C5:** Versioned brief cites inputs | **PASS** | yes if FAIL (default) |
| **C6:** Grounded draft / Null skeleton; unsupported warnings; paid=false | **PASS** | yes if FAIL |
| **C7:** Determinism + freezes (health, domain-match, SSRF, query-set-v3, quality-v1, provenance 4.1.1, AI-search vs LLM-mention) | **PASS** | yes if FAIL (default) |
| **C8:** SSRF held | **PASS** | yes if FAIL |
| **C9:** No paid DO | **PASS** | yes if FAIL |
| **C10:** Full suite + Phase 5 tests | **PASS** | yes if FAIL (default) |

**Merge recommendation:** **PASS** — blocking intents C1/C2/C4/C6/C8/C9 all PASS; C3/C5/C7/C10 PASS.

**Pytest (independent, at product SHA):** `205 passed, 1 skipped, 0 failed` in 3.85s  
**Phase 5 file:** `42 passed` (`tests/unit/test_content_optimization_phase5.py`)  
**Skipped:** `tests/unit/test_digitalocean_web_search.py::test_live_digitalocean_web_search_optional` (live paid DO; not run)

**Sibling JSON:** `docs/verification/VERIFY-PHASE5-CONTENT-OPTIMIZATION-2026-09-18.json`

---

## Commands run

```bash
git rev-parse HEAD
# 53e5d11f44ce7e4f9a2e0100007930eac9e9deff

# Confirmed equals PR #17 head.sha

python3 -m venv .venv && pip install -e ".[dev]"
pytest -q
# → 205 passed, 1 skipped, 2 warnings in 3.85s

pytest tests/unit/test_content_optimization_phase5.py -v
# → 42 passed

git diff origin/main...HEAD -- \
  src/aeo_mvp/security/ssrf.py \
  src/aeo_mvp/target_site.py \
  src/aeo_mvp/domains.py \
  src/aeo_mvp/scoring/health.py \
  src/aeo_mvp/visibility/digitalocean_web_search.py \
  src/aeo_mvp/queries/evidence.py \
  src/aeo_mvp/queries/quality.py \
  src/aeo_mvp/config.py
# → empty (DIFF_BYTES=0 each)

# Independent probes: page_intel hostname/provenance; ContentProvenance+QSQ-EVD;
# coverage honesty flags; gap evidence+deterministic sort; brief citations;
# Null/skeleton draft+unsupported; version pins; SSRF API matrix; paid DO off
```

---

## C1 — Page intel + provenance + hostname scope — **PASS**

**Assert intent:** `page-intel-v1` extraction stamps hostname-scope target match; observed signals when present; missing fields map via 4.1.1 `normalize_provenance` → `compatibility` (never invent observed).

### Evidence

- Code: `src/aeo_mvp/content/page_intel.py` (`_content_prov` → `normalize_provenance`); models `PAGE_INTEL_VERSION=page-intel-v1`.
- Independent Hashnode fixture probe: `schema_version=page-intel-v1`, `target_match_scope=hostname`, `hostname=nik-hil.hashnode.dev`, ≥1 `observed` signal; empty HTML title → `compatibility`.
- Evidence path: `tests/unit/test_content_optimization_phase5.py::test_c1_page_intel_provenance_hostname_scope` PASSED.

---

## C2 — generated≠observed; draft never enters observed stores — **PASS**

**Assert intent:** Content provenance enum includes `generated`; drafts stamp `content_provenance=generated`; `generated` normalizes to `compatibility` for QSQ-EVD (never counts as observed); content package does not persist drafts into crawl/observed stores.

### Evidence

| Check | Result |
| --- | --- |
| `ContentProvenance` ⊇ {observed, derived, compatibility, generated} | yes |
| Draft + unsupported claims provenance | `generated` |
| `normalize_provenance("generated")` | `compatibility` |
| `observed_evidence_classes` on generated fake evidence | empty set |
| Page intel signals include `generated` | no |
| Gap evidence provenances | {compatibility, derived} only |
| `session.add` in content pipeline/service | absent |

- Evidence path: `::test_c2_provenance_includes_generated_no_draft_to_observed` PASSED.

---

## C3 — Coverage from snapshot themes; coverage≠visibility≠health — **PASS**

**Assert intent:** Coverage themes derive from page snapshot (no Hashnode/niche hardcode); `page_coverage` is not AI visibility and not `health-v1`; `cite_miss` only with visibility observations.

### Evidence

- SaaS fixture topics include snapshot themes (`acmeflow` / `project` / …); `hashnode` absent from topic blob.
- `page_coverage_status("AcmeFlow team workflows")` → `full` with match.
- Gap report flags: `coverage_is_not_ai_visibility=true`, `coverage_is_not_health_v1=true`; `HEALTH_FORMULA_VERSION=health-v1` unchanged.
- Without visibility observations: no `cite_miss` enrichment.
- Evidence path: `::test_c3_coverage_from_snapshot_themes_no_niche_hardcode` PASSED.

---

## C4 — Evidence-backed gaps; deterministic prioritize — **PASS**

**Assert intent:** Every gap carries evidence + explanation with allowed provenances; gap ordering is deterministic (severity → type → id sort).

### Evidence

- Quantum-knitting queryset vs SaaS page: 3 gaps; all have evidence+explanation; provenances ∈ {observed, derived, compatibility}.
- Two builds: identical gap id order (`gap_absent_*`, `gap_structure_*`, `gap_qa_*`) and identical `to_dict()` lists.
- Code: `gaps.py` `gaps.sort(key=lambda g: (_sev_rank, _type_rank, g.id))`.
- Evidence path: `::test_c4_evidence_backed_gaps_only` PASSED.

---

## C5 — Versioned brief cites inputs — **PASS**

**Assert intent:** `opt-brief-v1` cites page-intel, gap-report, query-set versions and page URL; methodology id locked.

### Evidence

Independent docs fixture brief `input_citations`:

| Key | Value |
| --- | --- |
| `page_intel_version` | `page-intel-v1` |
| `gap_report_version` | `content-gap-v1` |
| `query_set_version` | `query-set-v3` |
| `page_url` | `https://docs.example/` |

- `CONTENT_OPTIMIZATION_METHODOLOGY == content-optimization-v1`.
- Evidence path: `::test_c5_versioned_brief_cites_inputs` PASSED.

---

## C6 — Grounded draft / Null skeleton; unsupported warnings; paid=false — **PASS**

**Assert intent:** Null default (`content_draft=false`) → empty body, `status=skipped_paid_false`; skeleton when drafting; unsupported claims required; no invented citations/ranking promises; paid flags false.

### Evidence

| Mode | writer | status | body | paid |
| --- | --- | --- | --- | --- |
| `generate_draft=False` | `null` | `skipped_paid_false` | empty | false |
| `generate_draft=True` | `deterministic_skeleton` | `generated` | grounded skeleton | false |

- Unsupported claims present with `support=unsupported`; `[needs_source]` / `NEEDS_SOURCE` markers; no `fake-study.example` / “guaranteed citation”.
- `result.paid_llm=false`, `result.paid_retrieval=false`.
- Evidence path: `::test_c6_grounded_draft_citations_refuse_ungrounded` PASSED.

---

## C7 — Determinism + freezes — **PASS**

**Assert intent:** Same inputs → identical pipeline dict; freezes held vs `main` for SSRF, domain-match, health, provenance 4.1.1, query-set-v3, quality-v1; AI-search protocol distinct from LLM-mention.

### Evidence

**Freeze paths** (`git diff origin/main...53e5d11`): all empty (0 bytes) for  
`ssrf.py`, `target_site.py`, `domains.py`, `health.py`, `digitalocean_web_search.py`, `queries/evidence.py`, `queries/quality.py`, `config.py`.

| Pin | Value |
| --- | --- |
| `HEALTH_FORMULA_VERSION` | `health-v1` |
| `MATCH_RULE_VERSION` | `domain-match-v1` |
| `QUERY_SET_VERSION` | `query-set-v3` |
| `QUALITY_VERSION` | `query-quality-v1` |
| `SELECTION_SEED_METHOD` | `sha256_seeded_tiebreak_v1` |
| `DISCOVERY_METHOD_V2` | `query-discovery-v2` |
| `INTENT_BUDGET_ID` | `intent-budget-v1` |
| `LLM_MENTION_PROTOCOL_VERSION` | `llm-mention-v1` |
| `AI_SEARCH_PROTOCOL_VERSION` | `ai-search-vis-v1` |
| Protocols distinct | yes |
| `normalize_provenance(unknown\|api_observation\|generated)` | `compatibility` |

- Personal-blog dual run: `a.to_dict() == b.to_dict()`.
- Evidence path: `::test_c7_determinism_and_null_draft_ok` PASSED (+ freeze diffs).

---

## C8 — SSRF held — **PASS**

**Assert intent:** Content-optimization `source_url` rejects unsafe URLs; SSRF module frozen vs `main`.

### Evidence

| URL | HTTP status | Mechanism |
| --- | --- | --- |
| `http://127.0.0.1/secret` | **400** | SSRF policy |
| `http://169.254.169.254/latest/meta-data` | **400** | SSRF policy |
| `http://localhost/admin` | **400** | SSRF policy |
| `http://[::1]/` | **400** | SSRF policy |
| `file:///etc/passwd` | **422** | schema: url must be http(s); also `assert_safe_public_url` → SSRFError |
| `ftp://example.com/` | **422** | schema: url must be http(s) |

- `is_obviously_unsafe_url` true for loopback / RFC1918 / metadata.
- Route: `POST /api/v1/content-optimization` → `assert_safe_public_url` / `is_obviously_unsafe_url` before fetch.
- `src/aeo_mvp/security/ssrf.py` DIFF_BYTES=0 vs `main`.
- Evidence path: `::test_c8_ssrf_held` PASSED.

---

## C9 — No paid DO — **PASS**

**Assert intent:** Default paid retrieval / paid LLM off; content package has no DigitalOcean import; Null/skeleton writers only when paid=false.

### Evidence

- `get_settings().paid_retrieval_opt_in is False`.
- Pipeline result: `paid_retrieval=false`, `paid_llm=false`; draft `paid_llm=false`.
- `rg digitalocean src/aeo_mvp/content/` → no hits.
- `resolve_draft_generator(generate_draft=False)` → `NullDraftGenerator`; `generate_draft=True` → `DeterministicSkeletonDraftGenerator`.
- Verifier ran no paid DigitalOcean APIs.
- Evidence path: `::test_c9_paid_do_off` PASSED.

---

## C10 — Full suite + Phase 5 tests — **PASS**

**Assert intent:** Full pytest green; Phase 5 suite present with C1–C10 tests and fixtures.

### Evidence

- Full suite: **205 passed, 1 skipped, 0 failed** (3.85s) at `product_commit_sha`.
- Phase 5: **42** test functions; `test_c1_*` … `test_c10_*` all present.
- Fixtures: `saas_product`, `docs_site`, `ecommerce`, `personal_blog`, `empty_page` + Hashnode `article_agent_loop.html`.
- Versions: `content-optimization-v1`, `opt-draft-v1`.
- Evidence path: `::test_c10_full_suite_and_phase5_tests_present` PASSED + independent `pytest -q`.
