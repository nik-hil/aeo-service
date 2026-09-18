# Independent verification — TargetSiteIdentity / domain-match-v1

**Date:** 2026-09-18  
**PR:** https://github.com/nik-hil/aeo-service/pull/2  
**Branch / SHA:** `cursor/target-site-identity-2e31` @ `54874df8c130fcdf8522eee263c70543e2e48fa2`  
**Base:** `main` @ `e2528cbf73a607db57d908b7b07a6bc17f3812b6`  
**Verifier:** independent cloud agent (does not trust Engineering claim of 93/1)

## Overall: **PASS**

| Gate | Result |
| --- | --- |
| A Identity core | **PASS** |
| B AI-search / competitors | **PASS** |
| C Audit metadata | **PASS** |
| D Regression | **PASS** |
| E Report | **PASS** (this document + JSON sibling) |

**Pytest (independent):** `93 passed, 1 skipped, 0 failed`  
**Skipped:** `test_live_digitalocean_web_search_optional` — requires `DO_MODEL_ACCESS_KEY` + `AEO_LIVE_RETRIEVAL_TEST=true` (no live paid DO run).

**PSL correction applied:** `hashnode.dev` is **not** PSL PRIVATE → `registrable_domain("nik-hil.hashnode.dev") == "hashnode.dev"` is **expected**. Fail condition is AI-search using bare PSL as target match key; that defect is fixed via hostname-scope `TargetSiteIdentity` + supplemental allowlist + `include_psl_private_domains=True`.

---

## Commands run

```bash
git fetch origin main
git rev-parse HEAD   # 54874df8c130fcdf8522eee263c70543e2e48fa2
git diff --stat origin/main...HEAD

python3 -m pip install -e ".[dev]"
# Manual Hashnode / lookalike matrix (see Gate A evidence)
python3 - <<'EOF'
# ... resolve_target_site_identity + target_match matrix ...
EOF

python3 -m pytest tests/unit/test_target_site.py \
  tests/unit/test_ssrf.py \
  tests/unit/test_digitalocean_web_search.py \
  tests/unit/test_scoring.py -v --tb=short
# → 65 passed, 1 skipped

python3 -m pytest --tb=line -q
# → 93 passed, 1 skipped, 2 warnings

python3 -m pytest -rs
# SKIPPED: Live DO retrieval test requires DO_MODEL_ACCESS_KEY and AEO_LIVE_RETRIEVAL_TEST=true
```

Diff vs `main` (identity / matching / competitors / AI-search / tests / docs): 16 files, +1313 / −59 — includes `src/aeo_mvp/target_site.py`, `domains.py`, DO provider, competitors, metrics, orchestrator, report, `DOMAIN_MATCHING.md`, `test_target_site.py`, DO tests.

---

## Gate A — Identity core — **PASS**

### A1 TargetSiteIdentity separate from `registrable_domain()` / PSL — PASS

- New module `src/aeo_mvp/target_site.py` defines `TargetSiteIdentity` + `target_match()` / `target_match_detail()`.
- `domains.py` documents: `registrable_domain()` is true PSL eTLD+1 and **not** the AI-search match key.
- Evidence: `docs/methodology/DOMAIN_MATCHING.md`; DECISIONS D023.

### A2 `registrable_domain(nik-hil.hashnode.dev) == hashnode.dev` — PASS

```
>>> registrable_domain("nik-hil.hashnode.dev")
'hashnode.dev'
>>> registrable_domain_public_only("nik-hil.hashnode.dev")
'hashnode.dev'
```

Unit: `test_psl_hashnode_is_platform_apex_not_naive_bug`.

### A3 Hostname-scope Hashnode matrix — PASS

Identity for seed `https://nik-hil.hashnode.dev/`:
`target_domain_scope=hostname`, `identity_kind=supplemental_multi_tenant`, `site_key=nik-hil.hashnode.dev`.

Manual + parametrized results:

| Candidate | Expect | Result |
| --- | --- | --- |
| `nik-hil.hashnode.dev` (own URLs) | MATCH | MATCH (`exact_hostname`) |
| `www.nik-hil.hashnode.dev` | MATCH | MATCH (`www_alias`) |
| `other-user.hashnode.dev` | FAIL | no_match |
| `hashnode.dev` | FAIL | no_match |
| `blog.hashnode.dev` | FAIL | no_match |
| `maliciousnik-hil.hashnode.dev` | FAIL | no_match |
| `blog.nik-hil.hashnode.dev` | FAIL | no_match |

### A4 `example.com` vs `malicious-example.com`; www policy — PASS

- Registrable-scope: `www.example.com` / `blog.example.com` MATCH; `malicious-example.com` FAIL.
- www: strip **one** leading `www.` only (`apex_normalize`); documented in `DOMAIN_MATCHING.md`; tested `test_apex_normalize_strips_one_www_only`, Hashnode/example matrices.

### A5 Label-boundary safe (no naive endswith) — PASS

`test_hashnode_no_endswith_lookalike`: `maliciousnik-hil.hashnode.dev.endswith("nik-hil.hashnode.dev")` is True, but `target_match` is False. Hostname scope uses exact `apex_normalize` equality only.

### A6 Allowlist + `include_psl_private_domains=True` — PASS

```python
# domains.py
_EXTRACTOR = tldextract.TLDExtract(
    suffix_list_urls=(),
    include_psl_private_domains=True,
)
# Runtime check: _EXTRACTOR.include_psl_private_domains == True
```

`SUPPLEMENTAL_MULTI_TENANT_PLATFORMS` includes `hashnode.dev` (+ wordpress/medium/substack/ghost/tumblr). Tested via identity defaults + github.io private-PSL contrast (`alice.github.io` stays tenant eTLD+1).

---

## Gate B — AI-search / competitors — **PASS**

### B7 Appeared/cited use TARGET SITE hostname scope, not bare PSL — PASS

`digitalocean_web_search.py` resolves `TargetSiteIdentity` and filters with `target_match(u, identity)` for citations and sources — not `registrable_domain` equality.

Mocked: `test_hashnode_publication_does_not_credit_platform_or_siblings` — sibling / platform apex URLs do not set cite/appear; audit `match_scope == "hostname"`.

`aggregate_ai_search_metrics` uses `target_domain_appeared` / `target_domain_cited` only (no mention→appearance fallback): `test_ai_search_aggregate_ignores_mention_when_flags_null`.

Legacy `domain_matches_target` remains PSL-only and is documented as **not** for AI-search appeared/cited.

### B8 PSL still available separately for audit — PASS

Identity / audit expose `registrable_domain` / `target_registrable_domain` alongside scope/hostname. `registrable_domain()` unchanged in meaning (true eTLD+1).

### B9 Competitors `site_key`: sibling Hashnode pubs not same site / no wrong self-count — PASS

`extract_competitor_domains` omits via `target_match`; drops same-registrable siblings on multi-tenant unless `include_platform_siblings`.  
`test_competitors_omit_target_via_match_not_psl_collapse`: target + `other-user.hashnode.dev` + `hashnode.dev` absent; `competitor.com` present. Rows include `site_key`, `raw_host`, `identity_kind`.

---

## Gate C — Audit metadata — **PASS**

### C10 Match/audit fields — PASS

`build_target_site_match_audit` includes: `scope` / `match_scope`, `hostname` / `target_hostname`, `registrable_domain` / `target_registrable_domain`, `matched_source_urls` / `matched_urls_appeared`, `appeared`/`cited` bools, `matches[]` with `matched` bool + `url` + `hostname_normalized` + `registrable_domain` + `match_reason`.

Provider stores `meta.target_site` + `meta.target_site_match`. Report builder adds `target_site` identity audit (diff vs main).

Manual check: sibling `other-user` excluded from `matched_source_urls` when only own URL matches.

---

## Gate D — Regression — **PASS**

### D11 Full pytest — PASS (independent counts)

```
93 passed, 1 skipped, 2 warnings in ~1.2–1.6s
```

Engineering claim of 93/1 **confirmed** by this run (not trusted a priori).

### D12 SSRF tests — PASS

`tests/unit/test_ssrf.py`: all collected cases PASSED in targeted run (blocked localhost/private/metadata/file/ftp; public example.com OK; redirect-to-private rejected).

### D13 health-v1 WEIGHTS unchanged — PASS

```python
WEIGHTS = {
    "technical": 0.25,
    "content": 0.25,
    "entity": 0.20,
    "structured_data": 0.15,
    "answerability": 0.15,
}
```

Identical to `origin/main:src/aeo_mvp/scoring/health.py`. `test_health_worked_example` still expects `70.0`.

### D14 No live paid DO experiment — PASS

Live test skipped (env gates unset). No paid DO call executed during verification.

---

## Gate E — Report — **PASS**

Artifacts:

- `docs/verification/VERIFY-TARGET-SITE-IDENTITY-2026-09-18.md` (this file)
- `docs/verification/VERIFY-TARGET-SITE-IDENTITY-2026-09-18.json`
- Runtime copies: `/opt/cursor/artifacts/pytest-full.txt`, `pytest-targeted.txt`, `manual-hashnode-matrix.txt`

---

## Top FAIL issues

**None.** All gates A–E PASS. No product defects found under the PSL-corrected criteria.

### Notes (non-failing)

- Opt-in `scope="registrable_domain"` on Hashnode still equates all `*.hashnode.dev` tenants (documented footgun; default remains hostname).
- `detect_citation` in `metrics.py` still uses PSL equality for the **LLM-mention** path (intentionally untouched per methodology).
- Main’s `domains.py` lacked `include_psl_private_domains=True`; this PR correctly enables it for private-suffix platforms (e.g. `github.io`).
