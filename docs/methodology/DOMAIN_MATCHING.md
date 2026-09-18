# Domain matching — target site identity (domain-match-v1)

**match_rule_version:** `domain-match-v1`  
**Date:** 2026-09-18  
**Status:** Binding (Architect + AI Evaluator + Researcher)

---

## Verdict

Default **match_scope = `hostname`** for publication-level AEO on multi-tenant
hosts. Crediting via platform apex / bare eTLD+1 (`hashnode.dev` for
`nik-hil.hashnode.dev`) is a methodology defect — reject those hits.

`registrable_domain()` remains **true Public Suffix List eTLD+1**. It is **not**
the AI-search target match key. Use `target_match()` / `TargetSiteIdentity`.

---

## Separation of concerns

| Concern | Key | Module |
| --- | --- | --- |
| Crawl same-host | Exact hostname (`same_host`) | `crawler/discover.py` |
| SSRF / lookalike | PSL eTLD+1 | `domains.registrable_domain`, `security/ssrf` |
| AI-search appeared/cited | Scope-aware `TargetSiteIdentity` | `target_site.target_match` |
| Competitors | Same `site_key()`; omit via `target_match` | `visibility/competitors.py` |
| LLM mention | Unchanged (`llm-mention-v1`) | `detect_mention` / `detect_citation` |
| Health | Untouched (`health-v1`) | `scoring/health.py` |

Identity is **classify-only**. It must never widen crawl to PSL scope.

---

## PSL facts (Researcher — do not “fix”)

| Host | True PSL eTLD+1 (private domains ON) | Notes |
| --- | --- | --- |
| `nik-hil.hashnode.dev` | `hashnode.dev` | `hashnode.dev` is **not** on PSL PRIVATE |
| `alice.github.io` | `alice.github.io` | Private suffix; must enable `include_psl_private_domains` |
| `blog.example.com` | `example.com` | Ordinary |

Same apex collapse as Hashnode (not PSL-private): `wordpress.com`, `medium.com`,
`substack.com`, `ghost.io`, `tumblr.com`.

PSL PRIVATE (when enabled) covers e.g. `github.io`, `gitlab.io`, `vercel.app`,
`netlify.app`, `pages.dev`, `blogspot.com`, `notion.site`, `framer.*`,
`webflow.io`, `herokuapp.com`, …

**Product fix for Hashnode:** hostname scope + supplemental allowlist — **not**
rewriting PSL math to invent `nik-hil.hashnode.dev` as eTLD+1.

**Second bug:** `tldextract` must use `include_psl_private_domains=True` so
`alice.github.io` does not collapse to `github.io`.

---

## TargetSiteIdentity (frozen at prepare)

| Field | Meaning |
| --- | --- |
| `seed_url` | Job base URL |
| `scheme` | `http` / `https` |
| `hostname` | Normalized host (lower, no trailing dot, port stripped) |
| `hostname_apex_normalized` | Hostname after stripping **one** leading `www.` |
| `origin` | Scheme + host + non-default port |
| `registrable_domain` | True PSL eTLD+1 (attribute only — not default match key) |
| `target_domain_scope` / `match_scope` | `registrable_domain` \| `hostname` \| `origin` |
| `multi_tenant_host` | On supplemental or PSL-private multi-tenant platform |
| `match_rule_version` | `domain-match-v1` |
| `identity_kind` | `ordinary` \| `supplemental_multi_tenant` \| `psl_private_multi_tenant` \| `platform_apex` |

---

## site_key / default scope policy

1. Enable PSL private domains on `registrable_domain()`.
2. Versioned supplemental allowlist (`multi-tenant-supplemental-v1`), **not** on
   PSL PRIVATE: `hashnode.dev`, `wordpress.com`, `medium.com`, `substack.com`,
   `ghost.io`, `tumblr.com` → default `match_scope` / `site_key` = **full
   hostname** (strip one `www.` only).
3. Ordinary domains → `site_key` = registrable eTLD+1; `match_scope` =
   `registrable_domain` (www normalize).
4. Reject / flag bare platform apex as a customer target where appropriate
   (`identity_kind=platform_apex`).
5. Detection = PSL private-on **+** supplemental list — **not** “>2 labels” alone.

Fail closed: if the leaf hostname sits under a supplemental platform apex, never
default to registrable-scope (would credit siblings). Explicit
`registrable_domain` opt-in is possible but unsafe on those platforms.

---

## Match rules (`domain-match-v1`)

Normalize host for compare: lowercase, strip trailing dot, strip **one** leading
`www.` only. Ignore scheme / port / path / query.

**Ban:** naive `endswith` / substring host matching.

### hostname-scope (DEFAULT for supplemental tenants)

Candidate H matches target T iff `apex_normalize(H) == apex_normalize(T)`.

No parents, siblings, or cousins.

| Candidate | Target `nik-hil.hashnode.dev` | Hit? |
| --- | --- | --- |
| `nik-hil.hashnode.dev` | | YES (`exact_hostname`) |
| `www.nik-hil.hashnode.dev` | | YES (`www_alias`) |
| `blog.nik-hil.hashnode.dev` | | NO |
| `other-user.hashnode.dev` | | NO |
| `hashnode.dev` / `www.hashnode.dev` | | NO |
| `maliciousnik-hil.hashnode.dev` | | NO |
| `nik-hil.hashnode.dev.evil.com` | | NO |
| Path/query on foreign host | | NO |
| Text-only brand mention, no matching URL | | NO (flags stay false) |

### registrable-scope (OPT-IN for multi-tenant; default for ordinary)

`registrable_domain(H) == target_registrable_domain`.

For `https://example.com`: YES `www.example.com`, `blog.example.com`
(`subdomain_of_registrable`); NO `malicious-example.com`.

For Hashnode, opt-in registrable would equate **all** `*.hashnode.dev` tenants —
do not use as default.

### origin-scope

Exact normalized origin equality (scheme + host + non-default port).

---

## Metrics (AI search only)

- `target_domain_appeared` = true iff ≥1 URL in `source_urls` matches under
  `match_scope` (structured citation URLs also count as appearance in the DO
  provider).
- `target_domain_cited` = true iff ≥1 structured citation URL matches under the
  **same** `match_scope`.
- Appearance ≠ citation; never collapse.
- Brand-token text mention does **not** set either flag.
- `aggregate_ai_search_metrics` must **not** fall back to `detected_mention` /
  `detected_citation` when `target_domain_*` is null.

LLM-mention path (`llm_*`, `detected_mention`, `detected_citation`,
`llm-mention-v1`) is untouched; keep `target_domain_*` null/unused there.

---

## Competitors

- Same `site_key()` for target and competitors.
- Omit target hits via `target_match`, not `PSL == target`.
- Hosted tenants never aggregate to platform apex.
- Drop platform apex / sibling tenants from competitor SOV unless
  `include_platform_siblings=True`.
- Store `raw_host` + `site_key` + `identity_kind` (+ example URL).

---

## Audit / report

**Report:** `target_site{…}` = full identity audit dict (includes `site_key`,
`match_scope`, `match_rule_version`).

**Per observation** `meta.target_site_match`:

```
appeared, cited, scope / match_scope, hostname, registrable_domain,
match_rule_version, target_hostname, target_registrable_domain,
matched_source_urls / matched_urls_appeared,
matched_citation_urls / matched_urls_cited,
matches[]: {url, hostname_normalized, registrable_domain, match_reason}
```

`match_reason` ∈ `{exact_hostname, www_alias, registrable_equal,
subdomain_of_registrable, exact_origin, no_match}`.

---

## Brand tokens

Do **not** use platform token `hashnode` (or other supplemental apex labels) as
the brand for tenant publication jobs. Prefer the tenant label (`nik-hil`) /
entity extraction.

---

## Freezes

- `registrable_domain()` meaning = true PSL eTLD+1 (private domains ON).
- SSRF unchanged.
- `health-v1` formula/weights frozen.
- No suffix/endswith target matching.
- No live paid DigitalOcean runs required for this change.
