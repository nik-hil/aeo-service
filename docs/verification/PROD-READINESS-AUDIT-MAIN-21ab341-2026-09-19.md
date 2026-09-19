# Production-readiness audit — aeo-service `main` @ `21ab341`

**Date:** 2026-09-19  
**Scope:** Read-only audit of entire service on current `main` (post PR #20 merge; tip includes squash `21ab341`).  
**Rules followed:** No product-code changes; no Phase 6; no paid live DO / Hashnode live validation; Gate G prior live proof cited, not re-run.

## Recommendation

**NOT READY — P0/P1 ISSUES FOUND**

| Severity | Count |
| --- | --- |
| **P0** | **4** |
| **P1** | **16** |
| P2 | 8 (non-blocking residuals) |

**Unpaid suite @ tip:** `pytest -q -rs` → **206 passed, 1 skipped**  
Skip reason (only recurring): `tests/unit/test_digitalocean_web_search.py:635` — Live DO requires `DO_MODEL_ACCESS_KEY` and `AEO_LIVE_RETRIEVAL_TEST=true`. **Do not remove.**

**Gate G live DO proof (authoritative; do not re-run):**
- `docs/verification/VERIFY-LIVE-PHASE4-HASHNODE-2026-09-18.md` — Overall **PASS (Gate G)**; verifier did not start a second paid run
- `docs/verification/VERIFY-LIVE-PHASE4-HASHNODE-2026-09-18.json` — `"gate_g": "PASS"`, `"paid_do_run_by_verifier": false`
- Supporting live bytes: `docs/verification/LIVE_PHASE4_HASHNODE_2026-09-18.{md,json}`
- Job `a24c1a42-faac-48da-80ae-c0b608650cbc`, hostname-scope Hashnode isolation, AI-search honesty PASS

---

## P0 findings (must fix before keyed / multi-worker exposure)

### P0-1 — Paid DO retrieval ignores `paid_retrieval_opt_in` / `paid_retrieval_ready`

| Field | Detail |
| --- | --- |
| **File / symbol** | `src/aeo_mvp/pipeline/orchestrator.py` · `JobOrchestrator.run` (~254–288, ~353–432); `_select_provider` (~81–134) |
| **Problem** | Comment + ADR-026 require paid DO only when opt-in ∧ ready QuerySet. Code passes the flag into discovery and **logs** when opt-in∧¬ready, then the non-`discovery_only` branch always calls `_select_provider`. With `provider=auto` and `DO_MODEL_ACCESS_KEY` set, DO is always constructed and `run_query` runs for every prompt×run. Verified: `_select_provider(..., {"paid_retrieval_opt_in": False})` still constructs `DigitalOceanWebSearchProvider`. |
| **Failure scenario** | Env has DO key; client `POST /jobs` with defaults (`paid_retrieval_opt_in` false). Job burns paid `web_search` (prompts × `runs_per_prompt`, often 20×3). |
| **Why it matters** | Cost control, ADR-026, Gate G FAIL trigger (“paid run without opt-in”). Default path can spend money silently. |
| **Recommended fix** | Before `_select_provider` / any retrieval provider: require `paid_opt_in and discovery.paid_retrieval_ready` for DO/`retrieval_enabled` providers; otherwise OpenAI llm_mention only if explicitly requested, or demo/skip with clear `experiment_kind`. Honor the log branch as a hard skip. |
| **Regression test** | Mock DO HTTP; `paid_retrieval_opt_in=False` → assert DO never called; opt-in True but queryset not ready → same; opt-in∧ready → DO called. |

### P0-2 — No API authentication on secret-bearing worker

| Field | Detail |
| --- | --- |
| **File / symbol** | `src/aeo_mvp/api/routes.py` (all `/api/v1/*`); no auth deps in app/schemas |
| **Problem** | Entire API is open. Job create + content-optimization can trigger outbound crawl and (given P0-1) paid providers using server-side keys. |
| **Failure scenario** | Anyone who can reach the service creates jobs / posts `source_url` fetches; burns crawl bandwidth and paid inference. |
| **Why it matters** | Production exposure of a keyed worker is unrestricted spend + SSRF surface against the server’s network view. |
| **Recommended fix** | Require API key / mTLS (or bind localhost-only + document); deny paid paths without auth even if env keys exist. |
| **Regression test** | Unauthenticated `POST /jobs` → 401; valid key → 202. |

### P0-3 — Concurrent / re-entrant job execution can corrupt results

| Field | Detail |
| --- | --- |
| **File / symbol** | `_run_pipeline` `routes.py` ~44–55; `JobOrchestrator.run` ~188–198 (no status claim); `Page` unique `(job_id,url)` in `db/models.py` |
| **Problem** | No compare-and-swap from `pending`→`crawling`, no lease, no “already running” guard. Evidence/observations/metrics have no per-job wipe on restart. |
| **Failure scenario** | Two workers (or retry + original) run the same `job_id`: duplicate analyzer evidence, partial observation sets, `IntegrityError` on pages, or mixed provider results; status races. |
| **Why it matters** | Report metrics become non-deterministic/wrong; unique constraint can mark job failed after partial paid spend. |
| **Recommended fix** | Atomic claim (`UPDATE … WHERE status='pending'`); on re-entry refuse; optionally delete orphaned child rows before rerun; single-flight lock. |
| **Regression test** | Two concurrent `run(job_id)` → exactly one executes pipeline; second no-ops or 409. |

### P0-4 — OpenAI provider collapses API failure into zero-mention “success”

| Field | Detail |
| --- | --- |
| **File / symbol** | `src/aeo_mvp/visibility/openai_compatible.py` · `run_query` (~95–150); `metrics.aggregate_llm_metrics` (~112–129); orchestrator observation loop |
| **Problem** | On HTTP ≥400 / exception: sets `meta["error"]=True`, returns `VisibilityObservation` with `detected_mention=False` (no raise). Aggregates treat it as a valid non-mention run. Report never reads `meta.error`. Opposite of DO honesty (DO raises). |
| **Failure scenario** | Key present but 401/429/timeout on all prompts → job **completed**, `llm_mention_rate=0.0`, looks like “site invisible” not “provider dead”. |
| **Why it matters** | Operators cannot distinguish provider outage from true zero visibility. |
| **Recommended fix** | Raise (or fail job / exclude errored runs from denominators); emit `provider_error_rate` / observation-level error; fail closed if all runs error. |
| **Regression test** | Mock 500/timeout → job `failed` **or** denominators exclude errors and report exposes error count; rate ≠ silent 0.0 success. |

---

## P1 findings

### P1-1 — `ContentGap` kind→type promotion broken; absent queries typed as `thin_coverage`

| Field | Detail |
| --- | --- |
| **File / symbol** | `ContentGap.__post_init__` `content/models.py` ~394–447; emitters `content/gaps.py` ~382–412 (`gap_type="query"` + `kind="missing_answer"`) |
| **Problem** | When `kind` is set and `gap_type` is legacy, mapped kind is never applied (`pass` at ~418–420). Verified: `ContentGap(kind='missing_answer', gap_type='query')` → wire `gap_type=thin_coverage` (not `missing_page`). FAQ: `kind=missing_faq, gap_type=qa_coverage` → `question_coverage_gap` (not `no_answer_block`). |
| **Failure scenario** | Absent-coverage gaps look like thin coverage; wrong remediation (`expand` vs `create_page`). |
| **Why it matters** | Phase 5 contract correctness; silent taxonomy failure. |
| **Recommended fix** | Prefer `GAP_KIND_TO_TYPE[kind]` when `gap_type` is legacy/default; emit sheet-native types at emit site; remove dead `pass`. |
| **Regression test** | Absent coverage → `gap_type=="missing_page"`; `kind=missing_faq` alone → `no_answer_block`. |

### P1-2 — Brief `add_faq` path dead for real FAQ gaps

| Field | Detail |
| --- | --- |
| **File / symbol** | `content/brief.py` · `build_optimization_brief` (~385–394) |
| **Problem** | Requires `g.gap_type == "no_answer_block"`, but FAQ gaps normalize to `question_coverage_gap` (P1-1). FAQ-only report → `action=expand_section`. |
| **Failure scenario** | Pages missing FAQ get expand-body guidance instead of FAQ/schema work. |
| **Why it matters** | Genre/FAQ optimization silently wrong. |
| **Recommended fix** | Fix gap typing (P1-1) **or** key off `kind == "missing_faq"`. |
| **Regression test** | Page with no FAQ → `brief.action == "add_faq"`. |

### P1-3 — Job `content_optimization` option is a no-op in the main pipeline

| Field | Detail |
| --- | --- |
| **File / symbol** | `JobOptions.content_optimization` `api/schemas.py` ~37 (default **True**); orchestrator / report builder — **no** `run_content_optimization` |
| **Problem** | Default job option claims Phase 5; only standalone `POST /content-optimization` runs it. |
| **Failure scenario** | Client enables Phase 5 via job options, reads `/report`, finds no page_intelligence / content_gaps / briefs / drafts. |
| **Why it matters** | Contract/docs vs product gap; false confidence. |
| **Recommended fix** | Wire pipeline+report when flag true, **or** default flag false and document endpoint-only until wired. |
| **Regression test** | Completed job with `content_optimization=true` includes authoritative report keys (or flag rejected until implemented). |

### P1-4 — `draft_paid=true` + API key crashes content-optimization (500)

| Field | Detail |
| --- | --- |
| **File / symbol** | `PaidLLMDraftGenerator.generate` `content/draft.py` ~269–281; route `content_optimization` |
| **Problem** | With opt-in + key, stub **raises** `RuntimeError`. Uncaught → HTTP 500. Sheet defines `DraftStatus=failed`. |
| **Failure scenario** | `POST /content-optimization` with `draft_paid`/`paid_llm_opt_in` true and `OPENAI_API_KEY` set → 500. |
| **Why it matters** | Breaks honest failed-draft contract; looks like outage. |
| **Recommended fix** | Catch → `OptimizedContentDraft(status="failed", paid=False, warnings=[…])`. |
| **Regression test** | Opt-in+key → 200 with `draft.status=="failed"`, no outbound LLM HTTP. |

### P1-5 — Skeleton FAQ JSON-LD embeds unsupported answer text

| Field | Detail |
| --- | --- |
| **File / symbol** | `DeterministicSkeletonDraftGenerator.generate` `content/draft.py` ~160–193 |
| **Problem** | Builds `FAQPage` `acceptedAnswer` from invented bridging sentences + `[NEEDS_SOURCE]`, while marking claims unsupported. |
| **Failure scenario** | Consumer pastes `schema_jsonld` into production → fabricated FAQ in structured data. |
| **Why it matters** | Schema must mirror visible content; disclaimer is easy to ignore. |
| **Recommended fix** | Omit FAQ/Article JSON-LD until answers are supported, or emit stubs without answer text. |
| **Regression test** | Skeleton draft: no FAQ schema with invented answers, or answers empty/`[NEEDS_SOURCE]` only. |

### P1-6 — `PageIntelligence.to_dict()` drops additives needed for gap replay

| Field | Detail |
| --- | --- |
| **File / symbol** | `PageIntelligence.to_dict` `content/models.py` ~291–325; consumers in `gaps.py` use headings/topics/answer_units/faq |
| **Problem** | Wire omits h1/headings/topics/faq/answer_units/signals. No `from_dict`. In-process OK; API-only consumers cannot reconstruct. |
| **Failure scenario** | Client stores API `page_intelligence`, re-runs gaps offline → empty blob → false absent/thin gaps. |
| **Why it matters** | Round-trip / replay honesty. |
| **Recommended fix** | Versioned wire including additives under `extract`, or document non-round-trippable + require raw HTML; add `from_dict` if promoting. |
| **Regression test** | `extract → to_dict → from_dict → gap report` fingerprint stable **or** explicit error if incomplete. |

### P1-7 — OpenAPI sketch drifts from Phase 5 / provider wire shape

| Field | Detail |
| --- | --- |
| **File / symbol** | `docs/api/openapi-sketch.yaml`; `ContentOptimizationResult.to_dict`; `JobOptions` |
| **Problem** | Sketch requires singular `gap_report`/`brief`/`draft`; code’s authoritative keys are plurals (+ singular aliases). Omits DO provider enums / Phase 4 opt-in fields. |
| **Failure scenario** | Generated clients drop plural keys or reject `provider: digitalocean_web_search`. |
| **Why it matters** | Integration breakage; false API contract. |
| **Recommended fix** | Align OpenAPI with live `to_dict()` + `JobOptions`; mark singular as deprecated aliases. |
| **Regression test** | Contract test: response contains required plural keys. |

### P1-8 — Content-optimization with empty/failed page HTML silently “succeeds”

| Field | Detail |
| --- | --- |
| **File / symbol** | `resolve_page_html` `content/service.py` ~66–87; empty path `page_intel.py` ~249–260 |
| **Problem** | Returns `page.html` even if None/fetch_error; pipeline emits empty intel + gaps with HTTP 200. |
| **Failure scenario** | Optimize against robots-blocked/failed page → misleading gap report as if page were thin. |
| **Why it matters** | Wrong remediation grounded on missing observation. |
| **Recommended fix** | If html missing → 409/400 with `fetch_error`; require explicit `allow_empty_html`. |
| **Regression test** | Job page `html=None` → 400/409, not 200 empty intel. |

### P1-9 — SSRF DNS rebinding TOCTOU (validate then connect by hostname)

| Field | Detail |
| --- | --- |
| **File / symbol** | `assert_safe_public_url` `security/ssrf.py` ~150–167; `fetch_url` `crawler/fetch.py`; acknowledged out-of-scope in `docs/security/SSRF.md` |
| **Problem** | DNS checked, then httpx resolves again. No IP pin. |
| **Failure scenario** | Attacker DNS: first lookup public, second → `169.254.169.254` / RFC1918. |
| **Why it matters** | Classic cloud SSRF residual. |
| **Recommended fix** | Connect to validated IP with `Host` header; re-validate after connect. |
| **Regression test** | Mock getaddrinfo public→private between validate and connect → fetch blocked. |

### P1-10 — URL userinfo persisted; weak create-time IP filter

| Field | Detail |
| --- | --- |
| **File / symbol** | `create_job_record` `orchestrator.py` ~643–668; `is_obviously_unsafe_url` `ssrf.py` ~131–147 |
| **Problem** | `http://user:pass@example.com/` stored verbatim. Decimal/hex IPs not “obviously unsafe” at create (blocked later at crawl DNS only). |
| **Failure scenario** | Credentials in SQLite/backups; odd IP forms accept then immediately fail. |
| **Why it matters** | Secret leakage; weak create-time gate. |
| **Recommended fix** | Persist only normalized URL (no userinfo); treat numeric/hex hosts unsafe at create or always full-validate. |
| **Regression test** | Create with userinfo → stored URL has no password; decimal loopback → 400 at create. |

### P1-11 — Partial visibility persistence on mid-experiment provider failure

| Field | Detail |
| --- | --- |
| **File / symbol** | `JobOrchestrator.run` observation loop ~415–469; except ~632–636 |
| **Problem** | Observations flushed per batch; DO raises → job `failed` with partial rows; no resume/idempotent observation keys. Interacts with P0-3 on retry. |
| **Failure scenario** | Fail on prompt 10/20 after 9 paid calls; retry duplicates or conflicts. |
| **Why it matters** | Cost + inconsistent audit artifacts. |
| **Recommended fix** | Unique `(config_id,prompt_id,run_index)`; on fail mark incomplete; retries reuse rows. |
| **Regression test** | Inject fail on Nth call → no duplicate rows on rerun. |

### P1-12 — LLM URL-citation still bare PSL (multi-tenant hole)

| Field | Detail |
| --- | --- |
| **File / symbol** | `visibility/metrics.py` · `detect_citation`; `openai_compatible.py` ~125; orchestrator passes `site_registrable_domain=identity.registrable_domain` |
| **Problem** | LLM path uses PSL equality. For `nik-hil.hashnode.dev`, domain is `hashnode.dev` → sibling/apex URLs count as citations. AI-search correctly uses `target_match`. |
| **Failure scenario** | Model cites `https://other-user.hashnode.dev/...` → `llm_url_mention_rate` true for tenant job. |
| **Why it matters** | Same Hashnode class of defect DOMAIN_MATCHING fixed for AI-search remains for LLM mention. |
| **Recommended fix** | Scope `detect_citation` with `TargetSiteIdentity` / `target_match`. |
| **Regression test** | Tenant job + sibling URL → `detected_citation=False`; own hostname → True. |

### P1-13 — Explicit `registrable_domain` scope on supplemental tenants credits siblings

| Field | Detail |
| --- | --- |
| **File / symbol** | `target_site.py` · `resolve_target_site_identity` (~232–242); DO forwards `context.target_domain_scope` when set |
| **Problem** | Auto-fail-closed unless `scope=` forced; explicit `scope="registrable_domain"` allows all `*.hashnode.dev` (+ apex). |
| **Failure scenario** | Caller sets scope registrable for Hashnode seed → sibling/apex match. |
| **Why it matters** | Undoes publication isolation if any client passes scope carelessly. |
| **Recommended fix** | Reject/override registrable scope for `supplemental_multi_tenant`, or require loud `allow_unsafe_platform_registrable=True`. |
| **Regression test** | Hashnode + `scope="registrable_domain"` stays hostname **or** refuses; sibling still no-match by default. |

### P1-14 — Total crawl failure still completes as “bad SEO”

| Field | Detail |
| --- | --- |
| **File / symbol** | `crawler/discover.py` `crawl_live`; analyzers; `report/builder.py` (`pages_crawled` only) |
| **Problem** | Failed fetches become `Page` rows with `fetch_error`; pipeline never sets `failed`. Report has no `crawl_ok` / `fetch_error_count`. |
| **Failure scenario** | DNS/timeout on homepage → `completed`, T1=0, low health — looks like bad SEO, not crawl outage. |
| **Why it matters** | Failure vs zero-quality indistinguishability for operators. |
| **Recommended fix** | If zero eligible pages, fail job or set `crawl_status=degraded` + caveat + counts. |
| **Regression test** | Mock all fetches errored → not silent “site quality zero” without crawl flag. |

### P1-15 — `prompt_set_id` frozen wrong for v2 discovery

| Field | Detail |
| --- | --- |
| **File / symbol** | `orchestrator._build_prompts` ~183–184 returns `"discovered-queries-v1"` when using discovered prompts |
| **Problem** | Always stamps v1 id even when discovery is `query-discovery-v2` / `query-set-v3`. Report caveat says compare only matching `prompt_set_id`. |
| **Failure scenario** | Cross-job comparison groups incompatible Phase 3 vs 4 sets under one id. |
| **Why it matters** | False rate comparisons. |
| **Recommended fix** | Stamp real method/set version (e.g. `query-set-v3`). |
| **Regression test** | v2 discovery job → `prompt_set_id` matches query-set version. |

### P1-16 — Observability gaps + missing failure-path tests

| Field | Detail |
| --- | --- |
| **File / symbol** | `logging_config.py`; sparse orchestrator logs; `tests/` gaps |
| **Problem** | Plain stdout, no structured `job_id` field, no metrics. Suite never asserts failed-job `error_message`, OpenAI error≠zero-rate, empty-crawl semantics, or concurrent jobs. Phase 5 tests accept `thin_coverage` OR `missing_page` — mask P1-1. |
| **Failure scenario** | P0-1/P0-4/P1-1/P1-14 ship green (206 pass). Multi-job process cannot filter one failure. |
| **Why it matters** | Regressions invisible; ops blind. |
| **Recommended fix** | Structured JSON logs with `job_id`/`phase`/`provider`; add failure-path + concurrency + taxonomy-strict tests. |
| **Regression test** | Caplog assert failure contains `job_id`; tests named under P0/P1 above. |

---

## Area-by-area report

### 1. Data contracts and provenance

**Classification:** P1 issues present (P1-1, P1-5, P1-6, P1-7).

| Artifact | Observed | Derived | Compatibility | Generated |
| --- | --- | --- | --- | --- |
| **PageIntelligence** | title/h1/headings/jsonld/answer units with locators | primary_topic, word_count, content_type heuristics | empty-html path; AnswerUnit maps generated→compatibility | never on page-intel wire |
| **ContentGap** | evidence may cite observed classes | gap_type/severity/coverage | legacy short types via `LEGACY_TYPE_TO_SHEET` | not used |
| **ContentOptimizationBrief** | — | outline/edit_ops/work_queue | researcher additives | — |
| **OptimizedContentDraft** | — | — | — | **always** `content_provenance="generated"` in `to_dict` |
| **CandidateQuery** | `source_evidence` when stamped observed | intent/confidence/templates | legacy synthetic evidence | — |
| **EvidenceRecord** | only if `normalize_provenance` → observed | heuristic/derived_metric/llm_assist → derived | missing/unknown → compatibility | never (drafts must not enter QSQ-EVD) |
| **SiteUnderstanding / SiteProfile** | crawl-backed EvidenceRef when stamped | field wrappers | legacy projection fillers | LLM path unimplemented (warning) |

**Confirmed healthy:** Version constants + dual version keys; draft forced `generated`; evidence trust boundary (`normalize_provenance` / Phase 4.1.1) coherent and tested; cite_miss gated on visibility observations.

**No-issue:** Literal GapType/BriefAction/DraftStatus enums match PHASE5 sheet; singular+plural aliases on result `to_dict` intentional.

**Wire/API gaps:** Page-intel additives dropped on serialize (P1-6); OpenAPI behind plurals/providers (P1-7); gap taxonomy promotion broken (P1-1).

**Test assessment:** Strong freeze tests for evidence provenance; Phase 5 gap-type asserts too loose (OR of correct+incorrect types).

---

### 2. Persistence and job lifecycle

**Classification:** P0-3, P1-11.

| Stage | Behavior |
| --- | --- |
| Create | `create_job_record` → `pending`; BackgroundTasks |
| Transitions | crawling→analyzing→scoring→experimenting→synthesizing→completed / failed |
| Transactions | flush throughout; success commit in `_run_pipeline`; failure commit inside orchestrator |
| Retries / idempotency | **none** |
| Concurrent claim | **none** |

**Confirmed healthy:** SQLite FK pragma; additive `migrate_schema`; `discovery_only`/`dry_run` zeros visibility calls; demo crawl isolated; failed jobs expose `error_message`; report 409 until completed; cascade delete-orphan; unique `reports.job_id`.

**No-issue:** Partial commit of failed status after exception is intentional for ops visibility.

**Test assessment:** No concurrency/idempotency tests (P1-16).

---

### 3. API behavior

**Classification:** P0-2, P1-3, P1-4, P1-7, P1-8.

| Route | Notes |
| --- | --- |
| `GET /health` | OK |
| `POST /jobs` | 202; cheap SSRF; `JobOptions` **extra=allow** |
| `GET /jobs/{id}` | 404 unknown; scores optional |
| `GET …/report` | 409 if not completed/failed; 404 missing report |
| `GET …/pages` | list without HTML body (good) |
| `POST /content-optimization` | **extra=forbid**; SSRF on `source_url`; draft flags OR’d; does not auto-call DO |

**Confirmed healthy:** Phase 5 endpoint forbids unknown fields; draft defaults off; paid LLM stub refuses network when key missing (skeleton fallback); long-running work async via jobs.

**No-issue:** CreateJob URL scheme validation; report not returned for in-flight jobs.

**Test assessment:** Basic API tests exist; `test_report_conflict_while_pending` accepts 200 **or** 409 (weak); no auth/failed-job assertions.

---

### 4. Security

**Classification:** P0-2 (auth), P1-9, P1-10; residual untrusted HTML sink (coupled to P0-2).

**Confirmed healthy:** Scheme allowlist; localhost/`.local`/metadata labels; private/link-local/reserved/CGNAT/`is_global`; IPv4-mapped unwrap; redirect hop revalidation; decimal/hex/IPv6-mapped loopback blocked at full assert; DO response sanitizer redacts auth-like keys; Authorization not written into DO `raw_response`; manual redirects (no blind follow); httpx logging quieted.

**No-issue (checked absent):** Blind `follow_redirects=True`; fabricating DO results without key; naive host `endswith` as sole AI-search match.

**Do not weaken:** SSRF public-IP requirements; DO no-fallback raises; draft `content_provenance=generated` force.

**Test assessment:** Strong SSRF unit coverage; rare env skip if live DNS fails for example.com (not the recurring skip).

---

### 5. External providers

**Classification:** P0-1, P0-4.

**Selection (`_select_provider`):** demo → Demo; explicit DO/OpenAI → require key or raise; `auto` → DO if key else OpenAI if key else Demo + `used_demo_fallback`.

**Confirmed healthy:** DO missing key / HTTP error / non-JSON / missing web_search tool → **raise**, no fabricate; discovery never calls DO; content path `paid_retrieval=False` hard-coded; Perplexity stub not in auto path; unpaid suite + intentional live skip.

**Gate G:** PASS on prior live Hashnode DO run (cited above). That run validated AI-search honesty / hostname scope / health — **not** the unpaid default-path opt-in gate (P0-1 remains).

**No-issue:** Explicit provider misconfig raises rather than silent wrong provider (when provider name unknown).

**Test assessment:** Excellent mocked DO honesty tests; **missing** orchestrator-level unpaid opt-in gate test (P0-1).

---

### 6. Query intelligence

**Classification:** P1-15; minor residuals as P2 (v1 `frozen_at`, UUID evidence_ids).

**Confirmed healthy:** Default `query-discovery-v2` → `query-set-v3` + `query-quality-v1`; deterministic selection with seeded tie-break only (no live PRNG in `select_v2`); fingerprint/replay exclude `frozen_at`/evidence IDs; `content_hash` composition; evidence trust boundary; paid retrieval never auto-run **inside discovery**; dry-run forces opt-in false; dedup score-then-id; intent budgets / topic caps / MMR ordered.

**No-issue (hidden nondeterminism checklist):** Sets/dicts used as membership only; selection sorts by confidence/tie-break/`query_id`; no external model in discovery; DB order not on discovery hot path.

**P2 residuals:** Legacy `query-set-v2`/`select.py` wall-clock `frozen_at`; `uuid4()` evidence_ids in full JSON dumps (fingerprint still stable).

**Test assessment:** Strong phase4/41/411 freeze + fingerprint tests; dual v1/v2 stacks increase policy-drift risk (see area 12).

---

### 7. Content optimization

**Classification:** P1-1, P1-2, P1-3, P1-4, P1-5, P1-6, P1-8.

**Confirmed healthy:** E2E shape crawl/html → page_intel → gap report → brief → draft; page-intel uses `normalize_provenance`; draft forced `generated`; paid LLM default null / stub refuses live calls when key missing; cite_miss only with visibility observations; anti-mix labels `coverage_is_not_ai_visibility` / `not_health_v1`; orchestrator never folds draft into health/discovery/QSQ-EVD.

**No-issue:** Generated→observed leak into health/discovery metrics (checked absent); null draft default; paid=false boundary on unpaid path.

**Test assessment:** Large Phase 5 suite (C1–C10 style); over-accepts wrong gap types; missing draft_paid+key→failed-draft and empty-html cases.

---

### 8. Health vs visibility semantic boundaries

**Classification:** P1-12 (LLM citation only). Health/AI-search separation **healthy**.

**Confirmed healthy:** health-v1 only T/C/E/S/A weights — no visibility/query-coverage/content-gap inputs; LLM vs AI-search separate experiment kinds and metric names; no appearance/citation fallback to brand mention when `target_domain_*` null; DO uses `target_match`; content page_coverage explicitly not health/visibility.

**No-issue:** Combining health with SOV/visibility scores; mislabeling AI-search as health; folding content gaps into H.

**Naming hazard (not formula merge):** Shared name `query_coverage` means different formulas per experiment kind — documented.

**Test assessment:** Strong AI-search honesty / health freeze tests; LLM multi-tenant citation under-tested.

---

### 9. Target-site identity

**Classification:** P1-13; AI-search default path **healthy**.

**Confirmed healthy (verified patterns):** Hashnode leaf → hostname + `supplemental_multi_tenant`; sibling/apex/lookalike/parent subdomain no match under hostname scope; www alias on tenant matches; ordinary registrable domain; `alice.github.io` private PSL isolation; competitors omit via `target_match`; no naive host `endswith` as sole match for AI-search.

**No-issue:** www strip (one leading); platform allowlist; aggregation `site_key`; lookalike `maliciousnik-hil...`.

**Test assessment:** Excellent `test_target_site.py` coverage for AI-search path.

---

### 10. Observability

**Classification:** P0-4, P1-14, P1-16.

**Operator debug path today:**
1. `GET /api/v1/jobs/{id}` → `status`, `error_message`, timestamps  
2. Process stdout traceback (`job %s failed`)  
3. `GET …/pages` → per-URL `fetch_error` / `status_code`  
4. Partial mid-experiment fail: DB observations + `failed` status  
5. **Missing:** structured logs by `job_id`, crawl-degraded flag, provider error counts in report, metrics backend

| Path | Failure vs zero-result distinguished? |
| --- | --- |
| DO transport/HTTP/no-web_search | **Yes** — raises → job `failed` |
| DO success, target never appears | **Yes** — `completed`, rates 0 with denominators |
| OpenAI API error | **No** — P0-4 |
| Crawl all pages error | **Partial** — often `completed` with low T1; only pages[].fetch_error |

**Confirmed healthy:** DO raise-on-fail; hard job failure persistence of `error_message`.

---

### 11. Test quality

| Signal | Result |
| --- | --- |
| Run @ `21ab341` | **206 passed, 1 skipped** |
| Sole recurring skip | Intentional paid/live DO — **keep** |
| xfails | None |
| Real behavior | Strong mocked DO + SSRF + target_site + discovery provenance; demo e2e |
| Overfit / loose asserts | Phase 5 gap_type OR; report-pending accepts 200\|409 |
| Gaps | Opt-in gate; OpenAI error; crawl-all-fail; concurrency; auth; draft_paid 500; taxonomy-strict |
| Pass-while-broken risk | **High** for P0-1 and P0-4 |

**Test assessment:** Contract/freeze coverage is strong; **operational and cost-control failure paths are thin**.

---

### 12. Code quality / maintainability

**P2 themes (non-blocking but increase footgun rate):**
- Dual v1/v2 query stacks (`generate`/`gate`/`select` vs `*_v2`) + duplicated leak-policy regexes; v1 still ships hardcoded AI-agent pack while v2 forbids it
- Legacy `domain_matches_target` exported beside `target_match`
- Fat modules: `JobOrchestrator.run`, `understanding/builder.py`, `content/gaps.py`
- ~25 `*-vN` version tokens; wrong stamp footgun (P1-15)
- `JobOptions.content_optimization=True` default without wiring (P1-3)
- Compat complexity: DiscoveryVersion aliases, evidence `compatibility`, dual QuerySet types

**Confirmed healthy:** Manageable import DAG; no hard cycles found; frozen health/domain-match contracts heavily locked by tests.

---

### 13. Classification summary

| ID | Sev | Area | One-liner |
| --- | --- | --- | --- |
| P0-1 | P0 | Providers / lifecycle | ADR-026 unpaid: DO runs whenever key+auto |
| P0-2 | P0 | API / security | No auth on secret-bearing API |
| P0-3 | P0 | Persistence | No job claim → concurrent corrupt work |
| P0-4 | P0 | Providers / observability | OpenAI errors → silent zero-mention success |
| P1-1 | P1 | Contracts / content | Gap kind→type: absent→`thin_coverage` |
| P1-2 | P1 | Content | `add_faq` brief action dead |
| P1-3 | P1 | API / content | Job `content_optimization` not wired |
| P1-4 | P1 | API / content | `draft_paid`+key → HTTP 500 |
| P1-5 | P1 | Content | Skeleton FAQ schema with unsupported answers |
| P1-6 | P1 | Contracts | Page-intel wire not round-trippable |
| P1-7 | P1 | API | OpenAPI behind Phase 5 wire |
| P1-8 | P1 | API / content | Empty HTML silently optimized |
| P1-9 | P1 | Security | DNS rebinding TOCTOU |
| P1-10 | P1 | Security | Userinfo persisted; weak create-time IP filter |
| P1-11 | P1 | Persistence | Partial observations / non-idempotent |
| P1-12 | P1 | Visibility / identity | LLM `detect_citation` PSL on multi-tenant |
| P1-13 | P1 | Target identity | Explicit registrable scope unsafe on Hashnode-class |
| P1-14 | P1 | Observability | Crawl-all-fail looks like bad SEO |
| P1-15 | P1 | Query / observability | `prompt_set_id` always `discovered-queries-v1` |
| P1-16 | P1 | Tests / observability | Missing failure-path tests + unstructured logs |

**P2 (selected):** v1 `frozen_at` wall-clock; UUID evidence_ids in full dumps; dual query policy stacks; legacy `domain_matches_target` export; shared `query_coverage` name across experiment kinds; fat orchestrator; version-token proliferation; `test_report_conflict_while_pending` non-determinism.

---

## Final recommendation

**NOT READY — P0/P1 ISSUES FOUND**

Blockers before exposing a keyed or multi-worker instance: **P0-1** (unpaid DO cost gate), **P0-2** (auth), **P0-3** (job claim), **P0-4** (OpenAI failure honesty). Highest product-correctness P1s after that: gap taxonomy **P1-1/P1-2**, LLM multi-tenant citation **P1-12**, and crawl/empty-html failure surfacing **P1-8/P1-14**.

Gate G prior live DO proof remains PASS for AI-search honesty on Hashnode hostname scope; it does **not** clear the unpaid default-path opt-in defect (P0-1).
