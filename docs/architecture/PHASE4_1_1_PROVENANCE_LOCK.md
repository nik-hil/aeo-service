# Phase 4.1.1 — Evidence provenance trust-boundary lock

**Status:** Binding (Architect)  
**Scope:** Corrective only. No Phase 5. Keep `query-set-v3` / `query-discovery-v2`.  
**Freezes:** `ssrf.py`, `target_site.py`, `domains.py`, `scoring/health.py`,
`visibility/digitalocean_web_search.py`; health-v1, domain-match-v1,
TargetSiteIdentity, AI-search vs LLM-mention, DO semantics, paid opt-in,
query-set-v3, query-discovery-v2, query-quality-v1, intent-budget-v1,
`selection_seed_method=sha256_seeded_tiebreak_v1`. No query-set-v4.

## Canonical helper

```text
normalize_provenance(raw) → observed | derived | compatibility
```

| Input | Output |
| --- | --- |
| `observed` / `derived` / `compatibility` | preserved |
| SiteProfile `heuristic` / `derived_metric` / `llm_assist` | **derived** |
| missing / empty / any other unknown | **compatibility** |
| identity / origin / structured-profile **presence** alone | **never** → observed |
| legacy SiteUnderstanding shims / fillers | **compatibility** |

**One** `normalize_provenance` is used by `EvidenceRecord.from_dict`,
`stamp_evidence_dict`, and `generate_v2` / `generate` adapters.

## Rules

1. **Never invent `observed`.** Missing/unknown → compatibility only.
2. Do **not** promote identity, origin, structured-profile presence, or legacy
   fillers to `observed`.
3. SiteProfile field provenances `heuristic` | `derived_metric` | `llm_assist`
   map to EvidenceRecord **`derived`** (do not count for QSQ-EVD).
4. Legacy / shim fillers → **`compatibility`**.
5. When an evidence item lacks provenance, adapters may inherit the parent
   SiteProfileField provenance and run it through `normalize_provenance`
   (heuristic → derived). Absence of both → compatibility.
6. Crawl `EvidenceRef` may stamp `observed` **only** as an explicit hard
   contract at construction (`builder._ref`); never inferred later from
   “this came from structured.” Field origin ≠ evidence provenance.
7. **QSQ-EVD** unchanged: ≥2 **distinct** classes with `provenance==observed`.
   Derived and compatibility do not count.
8. Generation may use weak (derived/compatibility) class presence for
   **viability**; honesty / accept-reject stays at `gate_candidates_v2`.

## QSQ-EVD examples

| Evidence | Strongest EVD |
| --- | --- |
| two distinct `observed` | **PASS** |
| two same-class `observed` | FAIL |
| observed + derived | FAIL |
| observed + compatibility | FAIL |
| derived-only / compatibility-only / missing | FAIL |

## Out of scope

- Phase 5
- Paid DigitalOcean calls
- Overwriting `VERIFY-PHASE4.1-CORRECTIVE-2026-09-18.*`
  (Verifier creates `VERIFY-PHASE4.1.1-PROVENANCE-*`)
