# Production-readiness RE-AUDIT — aeo-service `main` @ `e9bbad7`

**Date:** 2026-09-19  
**HEAD SHA:** `e9bbad730b82bcc488dadfa92bd49b03b624ef7c`  
**Tip commit:** `fix(P0-5): atomic single-job claim for concurrency`  
**Prior audit:** `docs/verification/PROD-READINESS-AUDIT-MAIN-21ab341-2026-09-19.md` (`21ab341`)  
**Scope:** Read-only re-audit. No product-code changes. No Phase 6. No paid live DO / live Hashnode.

---

## Verdict

**NOT READY — P1 WORK REQUIRED**

| Severity | Count |
| --- | --- |
| **P0** | **0** |
| **P1** | **13** (still present from prior) |
| **P2** | **4** (incl. 2 prior-P1 downgrades) |

All five expected P0 merge series items are **FIXED** (ADR-026 DO opt-in, SSRF IP-pin, API auth, OpenAI fail-closed, atomic job claim). Remaining blockers are product-correctness / honesty P1s, not new exploitable P0 spend/auth/concurrency defects.

---

## Suite & CI

```
pytest -q -rs  →  322 passed, 1 skipped  (9.54s)
```

**Skip (keep):** `tests/unit/test_digitalocean_web_search.py:635` — Live DO requires `DO_MODEL_ACCESS_KEY` and `AEO_LIVE_RETRIEVAL_TEST=true`.

**Targeted (SSRF/auth/provider-failure/job-claim/content-opt/integration):**

```
178 passed  (tests/unit/test_ssrf.py, test_api_auth.py, test_paid_retrieval_opt_in_gate.py,
             test_openai_provider_fail_closed.py, test_job_claim_concurrency.py,
             test_content_optimization_phase5.py, tests/integration/)
```

**CI:** **No GitHub Actions** (no `.github/workflows`). Suite is local/`pytest` only — process gap (P2), not a product defect.

**Gate G live DO proof (cited, not re-run):**  
`docs/verification/VERIFY-LIVE-PHASE4-HASHNODE-2026-09-18.md` — Overall **PASS (Gate G)**; `"paid_do_run_by_verifier": false`.

---

## Baseline inventory (this tip)

### Commits since prior audit (`21ab341` → `e9bbad7`)

| Commit | Label | Maps to prior finding |
| --- | --- | --- |
| `68d5a65` | P0-1 ADR-026 paid DO opt-in | Prior P0-1 |
| `0a34732` | P0-2 SSRF IP-pin | Prior **P1-9** (promoted) |
| `7dc5a8a` | P0-3 API auth | Prior P0-2 |
| `a2ac968` | P0-4 OpenAI fail-closed | Prior P0-4 |
| `e9bbad7` | P0-5 atomic job claim | Prior P0-3 |

### API routes (auth via `ApiAuthMiddleware`)

| Method | Path | Auth |
| --- | --- | --- |
| `GET`/`HEAD` | `/health` | **Public** |
| `POST` | `/api/v1/jobs` | Required |
| `GET` | `/api/v1/jobs/{job_id}` | Required |
| `GET` | `/api/v1/jobs/{job_id}/report` | Required |
| `GET` | `/api/v1/jobs/{job_id}/pages` | Required |
| `POST` | `/api/v1/content-optimization` | Required |
| `GET`/`HEAD` | `/openapi.json`, `/docs`, `/redoc` | Required |

### Job state machine

`pending`|`failed` → CAS → `claimed` → `crawling` → `analyzing` → `scoring` → `experimenting` → `synthesizing` → `completed`|`failed`.  
Module: `src/aeo_mvp/pipeline/job_claim.py`. Docs: `docs/architecture/JOB_CLAIM.md`.  
**Documented tradeoff:** no lease; crash after claim leaves durable `claimed` until operator reset.

### DB / sessions

Default SQLite `sqlite:///./aeo_mvp.db`; Postgres via `AEO_DATABASE_URL`. Claim commits before crawl/providers. Success commit in `_run_pipeline`; provider failure commits `failed` inside orchestrator.

### Outbound HTTP

| Path | Client | SSRF |
| --- | --- | --- |
| Crawl / robots / content-opt `source_url` | httpx via `fetch_url` | **IP-pinned** (`validate_url_for_fetch` + Host/SNI; no auto-redirect) |
| OpenAI `/chat/completions` | httpx to `OPENAI_BASE_URL` | Operator base URL trust boundary |
| DO `/responses` | httpx to `DO_INFERENCE_BASE_URL` | Operator base URL trust boundary |
| Paid LLM draft | — | Refuses live calls (`RuntimeError`) |
| Perplexity / site LLM assist | stubs | No network |

### Provider / spend defaults

- `AEO_PAID_RETRIEVAL_OPT_IN=false`; job `paid_retrieval_opt_in=false`
- DO only when `paid_opt_in ∧ paid_retrieval_ready` (ADR-026)
- `discovery_only` / `dry_run` force opt-in off and skip visibility
- `AEO_ENVIRONMENT=production`; `AEO_ALLOW_UNAUTHENTICATED` ignored outside local/dev/test
- Missing `AEO_API_KEY` → **401** (fail-closed)

---

## Prior P0 disposition

| Prior / commit | Finding | Status |
| --- | --- | --- |
| P0-1 / `68d5a65` | ADR-026 unpaid DO with key+`auto` | **FIXED** |
| P0-2 / `0a34732` (was P1-9) | SSRF DNS rebinding TOCTOU | **FIXED** |
| P0-3 / `7dc5a8a` (was P0-2) | No API auth | **FIXED** |
| P0-4 / `a2ac968` | OpenAI soft-fail → zero-mention success | **FIXED** |
| P0-5 / `e9bbad7` (was P0-3) | Concurrent job re-entry | **FIXED** |

**No REGRESSED prior P0s. No new P0 found.**

### Fix evidence (summary)

1. **ADR-026:** `_allow_paid_do_retrieval` + `_select_provider(..., allow_paid_retrieval=)` in `orchestrator.py`; explicit DO without opt-in raises; auto never constructs DO without gate. Tests: `test_paid_retrieval_opt_in_gate.py`.
2. **SSRF IP-pin:** `validate_url_for_fetch` → `ValidatedFetchTarget.validated_ips`; `_get_pinned` connects to IP with `Host` + TLS SNI; redirect hop re-validate. Tests: `test_ssrf.py` rebinding cases. Docs: `docs/security/SSRF.md`.
3. **API auth:** `ApiAuthMiddleware`; public allowlist `/health` only; prod bypass ignored; `secrets.compare_digest`. Tests: `test_api_auth.py`. Docs: `docs/security/API_AUTH.md`.
4. **OpenAI fail-closed:** typed `OpenAICompatibleError`; job → `failed` + redacted `error_message`; no `meta["error"]` soft path. Tests: `test_openai_provider_fail_closed.py`.
5. **Job claim:** CAS `UPDATE … WHERE status IN ('pending','failed')` → `claimed`, `rowcount==1`, commit before work; loser `JobClaimConflict` does not mark failed. Tests: `test_job_claim_concurrency.py`. Docs: `JOB_CLAIM.md`.

---

## Prior P1 disposition

| ID | Finding | Status | Severity now |
| --- | --- | --- | --- |
| P1-1 | ContentGap kind→type (`missing_answer`→`thin_coverage`) | **STILL PRESENT** | P1 |
| P1-2 | Brief `add_faq` dead (`no_answer_block` required) | **STILL PRESENT** | P1 |
| P1-3 | Job `content_optimization=true` unwired | **STILL PRESENT** | P1 |
| P1-4 | `draft_paid`+key → `RuntimeError` / HTTP 500 | **STILL PRESENT** | P1 |
| P1-5 | Skeleton FAQ JSON-LD with invented + `[NEEDS_SOURCE]` answers | **STILL PRESENT** | P1 |
| P1-6 | `PageIntelligence.to_dict` drops additives | **STILL PRESENT** | P1 |
| P1-7 | OpenAPI sketch drifts from live wire | **STILL PRESENT** | P1 |
| P1-8 | Empty job HTML content-opt → 200 empty intel | **STILL PRESENT** | P1 |
| P1-9 | SSRF DNS rebinding | **FIXED** (P0-2) | — |
| P1-10 | URL userinfo persisted; weak create-time IP filter | **STILL PRESENT** | P1 |
| P1-11 | Partial observations on mid-experiment fail; non-idempotent reclaim | **STILL PRESENT** | P1 |
| P1-12 | LLM `detect_citation` bare PSL (multi-tenant) | **STILL PRESENT** | P1 |
| P1-13 | Explicit `registrable_domain` scope on supplemental tenants | **STILL PRESENT** | **P2** (documented opt-in) |
| P1-14 | Total crawl failure completes as “bad SEO” | **STILL PRESENT** | P1 |
| P1-15 | `prompt_set_id` always `discovered-queries-v1` | **STILL PRESENT** | P1 |
| P1-16 | Observability + missing failure-path tests | **STILL PRESENT** (partially mitigated) | **P2** |

**REGRESSED:** none. **NO LONGER APPLICABLE:** none.

---

## Remaining P1 findings (detail)

### P1-1 — ContentGap kind→type promotion broken

| Field | Detail |
| --- | --- |
| **File** | `src/aeo_mvp/content/models.py` ~407–419 (`pass`); emitters `content/gaps.py` |
| **Failure** | `ContentGap(kind="missing_answer", gap_type="query")` → wire `thin_coverage` (verified @ tip). FAQ: `kind=missing_faq` → `question_coverage_gap` not `no_answer_block`. |
| **Impact** | Wrong remediation taxonomy |
| **Repro** | Instantiating gap as above; or FAQ-only page through gap builder |
| **Remediation** | Apply `GAP_KIND_TO_TYPE[kind]` when `gap_type` is legacy/default; emit sheet-native types at emit site |

### P1-2 — Brief `add_faq` path dead

| Field | Detail |
| --- | --- |
| **File** | `src/aeo_mvp/content/brief.py` ~387–394 |
| **Failure** | Requires `gap_type == "no_answer_block"`; FAQ gaps are `question_coverage_gap` → never `add_faq` |
| **Impact** | Missing-FAQ pages get expand/schema guidance instead of FAQ work |
| **Repro** | Verified: FAQ gaps present but `brief.action` not `add_faq` when schema gaps dominate; FAQ-only still fails `no_answer_block` check |
| **Remediation** | Fix P1-1 **or** key off `kind == "missing_faq"` |

### P1-3 — Job `content_optimization` option unwired (default True)

| Field | Detail |
| --- | --- |
| **File** | `api/schemas.py:37`; `JobOrchestrator` never calls `run_content_optimization` |
| **Failure** | Default job option claims Phase 5; `/report` has no page_intelligence / content_gaps / briefs / drafts |
| **Impact** | Contract lie; false confidence |
| **Classification** | Defect / contract drift (not a documented tradeoff) |
| **Remediation** | Wire pipeline+report **or** default flag `false` + document endpoint-only |

### P1-4 — `draft_paid=true` + API key → 500

| Field | Detail |
| --- | --- |
| **File** | `content/draft.py:280–281`; route `api/routes.py` content-optimization |
| **Failure** | `PaidLLMDraftGenerator(draft_paid=True, api_key=…).generate(...)` raises `RuntimeError` (verified); uncaught → HTTP 500 |
| **Impact** | Breaks honest `DraftStatus=failed` contract |
| **Remediation** | Catch → `OptimizedContentDraft(status="failed", …)`; return 200 |

### P1-5 — Skeleton FAQ JSON-LD embeds unsupported answer text

| Field | Detail |
| --- | --- |
| **File** | `content/draft.py:160–193` |
| **Failure** | Builds FAQPage `acceptedAnswer.text` from invented bridging sentence + `[NEEDS_SOURCE]` while marking claims unsupported |
| **Impact** | Paste-into-production structured-data risk. Note: `OptimizedContentDraft.to_dict` currently omits `faq`/`schema_jsonld` (partial API hiding) — generator object still builds publishable-looking schema |
| **Remediation** | Omit FAQ JSON-LD until supported, or empty/`[NEEDS_SOURCE]`-only answers |

### P1-6 — `PageIntelligence.to_dict` drops additives

| Field | Detail |
| --- | --- |
| **File** | `content/models.py` `PageIntelligence.to_dict` |
| **Failure** | Omits `h1`/`headings`/`topics`/`faq_coverage`/`answer_units`/`signals`; no `from_dict` |
| **Impact** | API round-trip cannot faithfully re-run gaps |
| **Remediation** | Versioned wire + `from_dict`, or document non-round-trippable |

### P1-7 — OpenAPI sketch drifts

| Field | Detail |
| --- | --- |
| **File** | `docs/api/openapi-sketch.yaml` vs live `to_dict` / `JobOptions` |
| **Failure** | Sketch requires singular `gap_report`/`brief`/`draft`; omits DO provider / Phase-4 opt-in fields (auth docs exist separately) |
| **Impact** | Generated clients drop plurals / reject `digitalocean_web_search` |
| **Remediation** | Align sketch with live wire; mark singular deprecated |

### P1-8 — Empty/failed page HTML silently “succeeds”

| Field | Detail |
| --- | --- |
| **File** | `content/service.py` returns `page.html` even if None; empty path in `page_intel.py` |
| **Failure** | Job page `html=None` → HTTP 200 + `warnings:["empty_page_html"]` + thin/absent-style gaps |
| **Partial fix** | Live `source_url` fetch failure → 502 |
| **Remediation** | Missing html → 400/409 unless `allow_empty_html` |

### P1-10 — URL userinfo persisted; weak create-time IP filter

| Field | Detail |
| --- | --- |
| **File** | `orchestrator.create_job_record` stores raw URL; `ssrf.is_obviously_unsafe_url` |
| **Failure** | `http://user:pass@host/` stored in `jobs.base_url` (`_normalize_url` strips userinfo but create does not use it). Decimal/hex IPs (`2130706433`) not obvious at create (verified `obvious=False`); blocked later at crawl DNS |
| **Impact** | Creds in DB/backups; weak create gate |
| **Remediation** | Persist normalized URL; treat numeric/hex hosts unsafe at create |

### P1-11 — Partial visibility persistence / non-idempotent reclaim

| Field | Detail |
| --- | --- |
| **File** | `orchestrator.py` observation loop; `VisibilityObservation` no unique `(config_id,prompt_id,run_index)`; claim reclaim does not wipe children |
| **Failure** | Provider raise mid-loop → `failed` + partial rows; `failed` reclaim can duplicate observations |
| **Impact** | Cost + inconsistent audit artifacts. P0-5 prevents dual *concurrent* owners; does not make observations idempotent |
| **Remediation** | Unique key + incomplete marker; wipe or reuse on reclaim |

### P1-12 — LLM URL-citation bare PSL (multi-tenant)

| Field | Detail |
| --- | --- |
| **File** | `visibility/metrics.py:46–58` `detect_citation`; orchestrator passes `identity.registrable_domain` |
| **Failure** | Verified: `detect_citation("https://other.hashnode.dev/x", "hashnode.dev")` → True |
| **Impact** | Sibling/apex URLs count as citations for Hashnode-class tenants (AI-search path correctly uses `target_match`) |
| **Remediation** | Scope with `TargetSiteIdentity` / `target_match` |

### P1-14 — Total crawl failure completes as “bad SEO”

| Field | Detail |
| --- | --- |
| **File** | `crawler/discover.py`; `report/builder.py` (`pages_crawled` only) |
| **Failure** | All pages `fetch_error` → job `completed`, near-zero health — looks like bad SEO not crawl outage |
| **Impact** | Failure vs zero-quality indistinguishability |
| **Remediation** | Fail or `crawl_status=degraded` + `fetch_error_count` when zero eligible pages |

### P1-15 — `prompt_set_id` frozen wrong

| Field | Detail |
| --- | --- |
| **File** | `orchestrator.py:216–217` → `"discovered-queries-v1"` whenever discovered nonempty |
| **Failure** | v2 / `query-set-v3` jobs stamp v1 id |
| **Impact** | Cross-job rate comparisons mix incompatible sets |
| **Remediation** | Stamp real method/set version (e.g. `query-set-v3`) |

---

## P2 / documented residuals

| ID | Item | Classification |
| --- | --- | --- |
| P1-13↓ | Explicit `scope=registrable_domain` on supplemental multi-tenant credits siblings | **Documented opt-in tradeoff** (auto path stays hostname-isolated) |
| P1-16↓ | Unstructured stdout logs; Phase-5 taxonomy asserts still loose (`thin_coverage` OR `missing_page`) | **Partially mitigated** by new P0 regression suites; remaining is ops/test quality |
| — | Crash after claim leaves `claimed` (no lease) | **Documented tradeoff** (`JOB_CLAIM.md`) |
| — | No GitHub Actions CI | Process gap |
| — | README still implies auto→DO whenever key set | Doc drift vs ADR-026 code |
| — | Content-opt unknown job/page → 400 vs jobs 404 | Mild API inconsistency |
| — | Operator `OPENAI_BASE_URL` / `DO_INFERENCE_BASE_URL` unrestricted | Accepted env trust boundary |
| — | Dead `maybe_digitalocean_provider()` helper (uncalled) | Dead code |

---

## Domain checklist (compressed)

### SECURITY
- API auth coverage: **OK** (fail-closed; docs/OpenAPI protected)
- Prod vs dev bypass: **OK**
- SSRF / IP pin / redirects / IPv4-mapped / CGNAT / metadata: **OK** for user-URL fetch path
- Secrets in logs/errors: redaction on job `error_message` present; auth never logs bearer
- Residual: P1-10 userinfo; create-time weak IP filter

### COST/PROVIDER
- DO paid gate: **OK** (key alone does not spend)
- Explicit DO without opt-in: fails closed
- discovery_only / dry-run: **OK**
- OpenAI fail-closed: **OK**
- Claim-before-expensive-work: **OK**
- Residual: P1-11 partial paid observations on mid-fail + reclaim

### JOB LIFECYCLE
- Atomic claim / second worker / completed re-exec guard: **OK**
- Crash after claim: documented stuck `claimed`
- Residual: P1-11 observation idempotency

### API/DATA
- Protected routes + health public: **OK**
- Report 409 while in-progress: **OK**
- Residual: P1-3 flag lie; P1-4 500; P1-7 OpenAPI drift; ID enumeration mitigated by auth (not per-tenant RBAC — auth-only by design)

### CONTENT OPT
- Standalone endpoint works; job flag unwired (P1-3)
- Provenance: draft forced `generated`; page-intel uses `normalize_provenance` — **OK**
- FAQ/JSON-LD publishability: P1-5
- NEEDS_SOURCE: present by design in skeleton
- AnswerUnit on object; wire via projections (P1-6 incomplete)
- cite_miss gated on visibility observations — **OK**
- queryset fingerprint set — **OK**
- null draft default — **OK**
- discovery_only — **OK**

### EVIDENCE/HONESTY
- No false SUCCESS on OpenAI/DO transport failure — **OK** (post P0-4)
- Demo fallback labeled — **OK**
- LLM multi-tenant citation still dishonest (P1-12)
- Crawl-all-fail looks like bad SEO (P1-14)
- Mid-run status progresses past `pending`; report 409 until completed — **OK**

### OPS
- Some `job_id=` log lines; not structured JSON
- Stuck-job detection: manual only (documented)
- Readiness vs liveness: single `/health` public endpoint
- No CI enforcement

---

## Residual documented risks (acceptable for this tip if P1s addressed later)

1. No job lease / heartbeat — operator must reset `claimed` after crash (`JOB_CLAIM.md`).
2. Explicit `registrable_domain` scope on Hashnode-class is an intentional footgun if callers opt in (P1-13→P2).
3. Provider HTTP clients trust operator-configured base URLs (not end-user SSRF).
4. Gate G live DO proof remains the unpaid-suite’s live evidence; not re-run here.

---

## Recommendation

Block production / keyed multi-worker exposure until the **remaining P1s** that affect contract honesty and multi-tenant correctness are addressed — highest urgency: **P1-3** (flag lie), **P1-1/P1-2** (gap taxonomy), **P1-12** (LLM citation), **P1-4** (500), **P1-14** (crawl failure surfacing).

P0 spend/auth/SSRF/claim/OpenAI honesty gates are cleared at `e9bbad7`.
