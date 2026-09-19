# Production-readiness FINAL audit — aeo-service

**Date:** 2026-09-19  
**FINAL MAIN SHA:** `e686a746b7222ea29f2652396398691ef3f9436d`  
**E-complete audited tree:** `2e18e843ae6b401fc73dbef06c2ca0c71eeff88c`  
**Base main before E:** `762db4e0b4d83e615e643a000baa928d50adcafb` (includes Workstream D PR #32)  
**Prior re-audit:** `docs/verification/PROD-READINESS-REAUDIT-MAIN-e9bbad7-2026-09-19.md` (`e9bbad7`)  
**Prior audit:** `docs/verification/PROD-READINESS-AUDIT-MAIN-21ab341-2026-09-19.md` (`21ab341`)  
**Scope:** Workstream E (low-risk P2/doc cleanup) + final classification of all original P0/P1/P2 IDs. No Phase 6. No live DO / Hashnode. No CI/lease/trusted-base-URL systems built.


---

## FINAL VERDICT

**READY WITH DOCUMENTED RESIDUAL RISKS**

All original P0s remain fixed. All product-correctness P1s from the re-audit are **FIXED** in code (Workstreams A–D + P1-3). Workstream E cleared safe doc/API/test leftovers. Remaining items are **accepted documented residuals** (ops/process/footguns), not contract or spend/auth defects.

---

## PRs CREATED / MERGED

| PR | Title | Status | Merge / tip |
| --- | --- | --- | --- |
| #22 | fix(P0-1): enforce ADR-026 paid DO opt-in gate | MERGED | `68d5a65` |
| #23 | fix(P0-2): pin SSRF outbound connects to validated IPs | MERGED | `0a34732` |
| #24 | fix(P0-3): fail-closed API authentication | MERGED | `7dc5a8a` |
| #25 | fix(P0-4): fail closed on OpenAI provider errors | MERGED | `a2ac968` |
| #26 | fix(P0-5): atomic single-job claim for concurrency | MERGED | `e9bbad7` |
| #27 | docs: production-readiness re-audit of main@e9bbad7 | MERGED | `a7d45a5` |
| #28 | fix(P1-3): wire content_optimization into job pipeline | MERGED | `6d4d07d` |
| #29 | fix(prod-A): content optimization contract + data integrity | MERGED | `e87e27e` |
| #30 | fix(prod-B): crawl/job honesty + observation idempotency | MERGED | `4f56260` |
| #31 | fix(prod-C): LLM citation uses TargetSiteIdentity | MERGED | `70b9e5b` |
| #32 | fix(prod-D): OpenAPI contract + prompt_set_id honesty | MERGED | `762db4e` |
| **#33** | **fix(prod-E) + final prod-readiness audit** | **OPEN (this PR)** | tip `e686a746b7222ea29f2652396398691ef3f9436d` |

---

## FULL TEST RESULT

```
pytest -q -rs  →  408 passed, 1 skipped  (≈15.7s)
```

### LIVE SKIPS (exact)

```
SKIPPED [1] tests/unit/test_digitalocean_web_search.py:635:
  Live DO retrieval test requires DO_MODEL_ACCESS_KEY and AEO_LIVE_RETRIEVAL_TEST=true
```

No other skips. Gate G live DO proof remains cited unpaid-suite evidence from
`docs/verification/VERIFY-LIVE-PHASE4-HASHNODE-2026-09-18.md` (not re-run).

---

## P0 confirmation (no regressions)

| P0 | Status | Code evidence |
| --- | --- | --- |
| P0-1 ADR-026 DO opt-in | **FIXED** (holds) | `JobOrchestrator._allow_paid_do_retrieval`; `_select_provider(..., allow_paid_retrieval=)` — auto never constructs DO without gate; explicit DO raises |
| P0-2 SSRF IP-pin | **FIXED** (holds) | `validate_url_for_fetch` → `ValidatedFetchTarget.validated_ips`; pinned connect + Host/SNI; redirect re-validate |
| P0-3 API auth | **FIXED** (holds) | `ApiAuthMiddleware`; `/health` public only; missing key → 401; prod ignores unauth bypass; `secrets.compare_digest` |
| P0-4 OpenAI fail-closed | **FIXED** (holds) | `OpenAICompatibleError` → job `failed` + redacted `error_message`; no soft zero-mention SUCCESS |
| P0-5 Atomic claim | **FIXED** (holds) | `claim_job` CAS `pending`/`failed`→`claimed`, `rowcount==1`, commit before work; loser `JobClaimConflict` |

**SECURITY / COST REGRESSIONS:** none observed. DO key alone does not spend. Auth fail-closed. SSRF pin intact. Claim-before-expensive-work intact.

---

## P1 classification (vs re-audit @ `e9bbad7`)

| ID | Finding | Classification | Evidence |
| --- | --- | --- | --- |
| P1-1 | Gap kind→type (`missing_answer`→`missing_page`, FAQ→`no_answer_block`) | **FIXED** | `ContentGap.__post_init__` + `GAP_KIND_TO_TYPE`; emit sites in `gaps.py` (PR #29) |
| P1-2 | Brief `add_faq` dead | **FIXED** | `brief.py` keys off `kind==missing_faq` / `no_answer_block` (PR #29) |
| P1-3 | Job `content_optimization` unwired | **FIXED** | Orchestrator → `optimize_job_pages` / report plurals (PR #28) |
| P1-4 | `draft_paid`+key → HTTP 500 | **FIXED** | `PaidLLMDraftGenerator` → `status=failed` draft, no raise (PR #29) |
| P1-5 | Skeleton FAQ JSON-LD invented answers | **FIXED** | FAQPage omitted unless source-backed; no invented answer text (PR #29) |
| P1-6 | `PageIntelligence.to_dict` drops additives | **FIXED** | `to_dict`/`from_dict` round-trip (PR #29) |
| P1-7 | OpenAPI sketch drift | **FIXED** | `openapi-sketch.yaml` aligned + drift tests (PR #32) |
| P1-8 | Empty HTML → 200 thin intel | **FIXED** | 400/409 unless `allow_empty_html` (PR #29) |
| P1-9 | SSRF DNS rebinding | **FIXED** (as P0-2) | IP-pin path |
| P1-10 | URL userinfo + weak create IP filter | **FIXED** | `normalize_public_url` persist; decimal/hex IP reject at create (PR #30) |
| P1-11 | Partial observations / non-idempotent reclaim | **FIXED** | Unique `(config,prompt,run)`; wipe-before-reclaim; rollback on provider fail (PR #30) |
| P1-12 | LLM citation bare PSL (multi-tenant) | **FIXED** | `detect_citation` → `target_match` / `TargetSiteIdentity` (PR #31) |
| P1-13 | Explicit `registrable_domain` scope opt-in | **ACCEPTED RESIDUAL DOCUMENTED** | Intentional footgun; auto path stays hostname-isolated (`DOMAIN_MATCHING.md`) |
| P1-14 | Total crawl failure as “bad SEO” | **FIXED** | `crawl_status=failed` → job fails (PR #30) |
| P1-15 | `prompt_set_id` frozen `discovered-queries-v1` | **FIXED** | `_prompt_set_id_from_discovery` stamps `query_set_version` (PR #32) |
| P1-16 | Observability + loose Phase-5 taxonomy asserts | **ACCEPTED RESIDUAL DOCUMENTED** (taxonomy **FIXED** in E) | Unstructured stdout logs remain; empty-page assert tightened in E |

**NOT FIXED P1s:** none (product P1s).

---

## P2 / residual classification

| Item | Classification | Notes |
| --- | --- | --- |
| README auto→DO whenever key | **FIXED** (E) | README + `AI_SEARCH_VISIBILITY_DO.md` document ADR-026 gate |
| Content-opt unknown job/page 400 vs jobs 404 | **FIXED** (E) | Unknown → 404; empty HTML stays 409; OpenAPI 404 documented |
| Loose Phase-5 taxonomy OR assert | **FIXED** (E) | `test_o_empty_page_fixture_pipeline` requires `structure_gap`; rejects `thin_coverage`/`missing_page` |
| Dead `maybe_digitalocean_provider()` | **ACCEPTED RESIDUAL DOCUMENTED** | Unused by orchestrator/routes/content; retained for Phase 4.1.1 freeze identity of `digitalocean_web_search.py` |
| P1-13↓ registrable opt-in | **ACCEPTED RESIDUAL DOCUMENTED** | Documented multi-tenant footgun |
| P1-16↓ unstructured logs | **ACCEPTED RESIDUAL DOCUMENTED** | No structured observability system (not built by design in E) |
| Crash-after-claim no lease | **ACCEPTED RESIDUAL DOCUMENTED** | `JOB_CLAIM.md` — operator reset required |
| No GitHub Actions CI | **ACCEPTED RESIDUAL DOCUMENTED** | Process gap; suite is local `pytest` only |
| Operator `OPENAI_BASE_URL` / `DO_INFERENCE_BASE_URL` unrestricted | **ACCEPTED RESIDUAL DOCUMENTED** | Env trust boundary (not end-user SSRF) |

---

## Workstream E changes (this PR)

1. Docs: `provider=auto` selection requires DO key **and** `paid_retrieval_opt_in` ∧ ready QuerySet.
2. API: `POST /content-optimization` unknown job/page → **404** (jobs-aligned).
3. Tests: tighten empty-page gap taxonomy; Workstream E regression suite.
4. OpenAPI: document content-opt **404**.
5. Dead helper: **not removed** (freeze); documented residual + unused-by-app assert.

---

## Domain checklist (final)

| Domain | Status |
| --- | --- |
| SECURITY (auth, SSRF pin, secrets) | **OK** — residuals: P1-13 opt-in, operator base URLs, userinfo fixed |
| COST/PROVIDER (DO gate, OpenAI fail-closed, claim-before-spend) | **OK** — residuals: none material |
| JOB LIFECYCLE (atomic claim) | **OK** — residual: no lease |
| API/DATA (contracts, OpenAPI, content-opt) | **OK** |
| CONTENT OPT (wired, taxonomy, drafts) | **OK** |
| EVIDENCE/HONESTY (crawl fail, citation, prompt_set) | **OK** |
| OPS (CI, structured logs, lease) | **Documented residuals** |

---

## P1s FIXED / REMAINING

- **FIXED:** P1-1, P1-2, P1-3, P1-4, P1-5, P1-6, P1-7, P1-8, P1-9, P1-10, P1-11, P1-12, P1-14, P1-15; P1-16 taxonomy half
- **REMAINING (accepted residual):** P1-13 (documented opt-in), P1-16 observability (unstructured logs)

## P2s FIXED / REMAINING

- **FIXED:** README ADR-026 drift; content-opt 404 consistency; Phase-5 loose taxonomy assert
- **REMAINING (accepted residual):** no CI; no lease; operator base URL trust; dead freeze-retained helper; unstructured logs; P1-13 footgun

---

## Recommendation

Ship as **READY WITH DOCUMENTED RESIDUAL RISKS** after CoS merges PR #33.
Do **not** block on CI/lease/observability/trusted-base-URL work unless ops requirements change.
