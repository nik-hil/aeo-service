# Query discovery methodology

**Versions:**  
- Phase 3: `query-discovery-v1` / `query-set-v2`  
- Phase 4 (default): `query-discovery-v2` / `query-set-v3` / `query-quality-v1` / `intent-budget-v1`

## Goals

Produce **representative, high-quality, non-redundant, reproducible, explainable**
query sets for AI-search visibility experiments on **arbitrary websites**.

Diagnostics judge the **query set**, not website quality. Never fold into `health-v1`.
Do **not** optimize queries to raise visibility %.

## Freezes

SSRF, TargetSiteIdentity / domain-match-v1, health-v1, LLM-mention vs AI-search split,
DigitalOcean provider honesty, paid retrieval opt-in default OFF.

## Pipeline (v2)

```
crawl snapshot → SiteProfile → candidate-gen-v2 (30–50 or small-site grace)
  → normalize + lexical near-dup (Jaccard / 3-gram / optional simhash)
  → query-quality-v1 gate → coverage selection (intent budgets → MMR → topic caps)
  → query-set-v3 + representativeness-v1
  → [discovery_only stop] OR [paid opt-in → visibility]
```

## Seeds

Accept aliases: `selection_seed` | `query_selection_seed` | `experiment_seed`.  
Persist `root_seed`, `effective_seed`, `seed_resolution` (source + alias).

## Candidate generation (v2)

- Generic template families from SiteProfile topics/entities/products/genre.
- **No** niche regex packs or hostname special-cases in core (`candidate-gen-v2`).
- Small-site grace: adaptive pool 12–25 with `grace_mode` — never fabricate topics.
- Reject double-interrogative wraps at generation time.

## Dedup

1. NFKC → lower → collapse whitespace (display normalize).  
2. Equality: strip trailing `?/.` + optional lead-in strip.  
3. Token Jaccard ≥ 0.85; char 3-gram Dice ≥ 0.80; sorted token signature.  
4. Optional `simhash_v1` (local CPU). **No paid embeddings required.**

## Quality gate (`query-quality-v1`)

Decomposable dimensions → accept | reject | accept_with_warning.  
Includes grammaticality lint (title-wrap / double-interrogative → fail).  
See `QUERY_SET_QUALITY.md`. **Not** a website ranking score.

## Selection (`query-set-v3`)

1. Hard intent budgets (`intent-budget-v1`, genre-conditioned).  
2. Prefer uncovered (topic × intent) cells.  
3. Lexical MMR λ ≈ 0.65.  
4. Max-per-topic ≤ 3–4 for k ≈ 20.  
5. Deterministic tie-break: effective_seed ordering via stable sort on confidence + `query_id`.

## Dry-run / reproducibility

- `discovery_only` / `dry_run`: persist full candidates + gate decisions + fingerprint;
  **zero** paid provider calls.
- Same snapshot + seed + versions → identical ordered query_id/text (`fingerprint`).
- Paid path requires ready QuerySet + opt-in (+ content_hash binding).

## Select prior version

`options.query_discovery_version=v1` keeps Phase 3 generate/gate/select interpretable.

## Metrics

Intent / topic / entity breakdowns + representativeness report — descriptive only.
