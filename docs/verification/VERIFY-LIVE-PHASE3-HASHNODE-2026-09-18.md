# Independent Verification — LIVE Phase 3 Hashnode (2026-09-18)

**Overall: PASS**  
**Verifier:** independent AEO Verifier (do not trust Engineering/CoS claims)  
**Verified at:** 2026-09-18 16:11:44 IST  
**Job:** `970aefc3-7d5a-4465-b0a8-79cb3e885458`  
**URL:** https://nik-hil.hashnode.dev/  
**Commit claimed / observed HEAD:** `7ac08ef` / `7ac08ef102eb34f9998c8078155fe7072e87c18b` (match)  
**Status / demo_mode:** completed / false  
**New paid DO run:** NO (artifacts + DB sufficient)

## Sources (independent)

| Artifact | Path |
|---|---|
| Summary | `/tmp/aeo_live_phase3_summary.json` |
| Report | `/tmp/aeo_live_phase3_report.json` |
| Docs live dump | `/workspace/aeo-service/docs/verification/LIVE_PHASE3_HASHNODE_2026-09-18.json` |
| DB | `/workspace/aeo-service/aeo_mvp.db` |

Summary ≡ docs live dump (same sha256 prefix `c6e1a80cbad9b73f`). Counts below recomputed from JSON audits + SQLite rows.

## Computed counts

| Metric | Value |
|---|---|
| candidates | **29** |
| selected (queries list) | **20** |
| observations | **20** |
| appeared (target) | **15** |
| cited (target) | **15** |
| matched_appeared_hosts | `nik-hil.hashnode.dev`: **43** |
| matched_cited_hosts | `nik-hil.hashnode.dev`: **43** |
| competitor_site_keys | arxiv.org, hashnode.com, github.com, dev.to, towardsdatascience.com |
| pages_crawled | 20 |
| health (recomputed) | **76.40625** (reported 76.4, health-v1) |

## Gates

### A) SiteProfile — **PASS**
- `site_genre` = `personal_tech_blog` (NOT `project_management`)
- Industry: `ai_ml` **present** (`omitted=false`, confidence 0.4) with article_body/title_h1 evidence (Agents Zero to Hero / AI Agent Permissions) — **evidence-backed**, not omitted, **not chrome-driven PM**
- Zero PM chrome terms in site_understanding blob
- Method: `deterministic_html_v1+site-profile-v1`; `llm_used=false`

### B) Query discovery — **PASS**
- **29 → 20** selected via `query-discovery-v1` (`query-set-v2`)
- `accepted_count=29`, `rejected_count=0`, `fallback_used=false`
- Intent breakdown (selected): informational 4, problem_solving 8, recommendation 4, comparison 3, navigational 1
- `paid_retrieval_opt_in=true` **explicitly** in `jobs.options_json.paid_retrieval_opt_in` (also on discovered_queries / query_set). Default elsewhere is false (`AEO_PAID_RETRIEVAL_OPT_IN` / Field default).

### C) TargetSiteIdentity — **PASS**
- hostname scope: `match_scope=hostname`, `target_domain_scope=hostname`
- registrable: `hashnode.dev`
- `identity_kind=supplemental_multi_tenant`
- `site_key=nik-hil.hashnode.dev`, `multi_tenant_host=true`, `match_rule_version=domain-match-v1`

### D) Visibility hosts — **PASS**
- Matched appeared/cited hosts: **only** `nik-hil.hashnode.dev` (43/43 URL hits across 15/15 obs)
- Zero `hashnode.dev` apex or sibling blog **credits**
- Note: raw DO `source_urls` included siblings (`xbstack`, `pragmatic-engineer`, `quokkalabs`.hashnode.dev) and `hashnode.com` — correctly **not** matched under domain-match-v1

### E) Experiment kind — **PASS**
- `experiment_kind=ai_search_visibility`, `retrieval_enabled=true`, protocol `ai-search-vis-v1`
- Provider `digitalocean_web_search` / `openai-gpt-4o`
- Report does **not** emit `llm_mention_rate` (correct for retrieval-enabled runs)
- `demo_mode=false`, job `status=completed`

### F) Freeze intact — **PASS**
- **SSRF:** `src/aeo_mvp/security/ssrf.py` present; fetch/discover/orchestrator import guards
- **domain-match-v1:** `MATCH_RULE_VERSION` + hashnode in supplemental allowlist; job metas tagged `domain-match-v1`; identity not regressed to registrable/apex credit
- **health-v1:** weights T0.25/C0.25/E0.20/SD0.15/A0.15 unchanged; recomputed **76.40625** == DB breakdown
- **LLM-mention semantics:** this job is not llm-mention; mention metrics not mixed into AI-search report block

## Limitations
- Candidate pool of 29 is taken from job artifacts/DB counters; full candidate member list beyond the selected 20 is not fully expanded in summary (accepted_count=29, rejected=0).
- options.selection_seed=42 vs query_set.selection_seed=11607312 (derived/internal); not a gate failure.
- Content component stored as 69.625; report/summary display may round to 69.6.
- Did not re-invoke DigitalOcean paid retrieval; verified existing observations only.
- SSRF/domain-match/health freeze checked via code spot-check + job outputs, not full pytest re-run in this verify pass.

## Notes
- summary JSON byte-identical to docs LIVE_PHASE3 artifact (sha256 prefix c6e1a80cbad9b73f).
- competitors.include_platform_siblings=false; 5 competitor keys none are hashnode.dev apex tenants credited as target.
- Industry ai_ml is evidence-backed from AI agent article titles/body — not chrome/nav PM misclassification.

## Machine-readable
See `VERIFY-LIVE-PHASE3-HASHNODE-2026-09-18.json`.
