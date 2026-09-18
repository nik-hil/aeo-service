# Phase 4 — Query Intelligence, Representativeness & Experiment Reproducibility

**Protocol:** `query-discovery-v2` · `query-quality-v1` · `query-set-v3` · `intent-budget-v1`  
**Status:** Implemented (dry-run first; paid live after Verifier A–F)

## Product goal

Make query sets for AI-search visibility **representative, high-quality,
non-redundant, reproducible, explainable** for arbitrary websites.
Diagnostics ≠ website quality; never fold into health-v1.

## Module map

| Module | Role |
| --- | --- |
| `queries/seed.py` | Alias resolution → root/effective seed |
| `queries/generate_v2.py` | Generic candidate families (`candidate-gen-v2`) |
| `queries/normalize.py` | Lexical / 3-gram / optional simhash near-dup |
| `queries/quality.py` | `query-quality-v1` diagnostics |
| `queries/intent_budget.py` | `intent-budget-v1` |
| `queries/select_v2.py` | Coverage + MMR → `query-set-v3` |
| `queries/representativeness.py` | `representativeness-v1` report |
| `queries/discovery.py` | Version switch v1/v2; persist candidates |

Frozen: `security/ssrf`, `target_site`, `scoring/health`, DO provider internals.

## Job options

```json
{
  "query_discovery_version": "v2",
  "selection_seed": 42,
  "discovery_only": true,
  "paid_retrieval_opt_in": false,
  "semantic_dedup": "lexical",
  "query_top_n": 20
}
```

## Phase 3 defects addressed

1. Seed aliases (`selection_seed` et al.) + persisted resolution.  
2. Grammaticality lint rejects title-wrap garbage.  
3. No AI-agent/Hashnode hardcoded packs in v2 generator.  
4. Candidate pool targets 30–50 with small-site grace; stage counts separated.  
5. Hard intent budgets.  
6. Coverage-aware selection + max-per-topic.  
7. Full candidates/rejected lists persisted for dry-run audit.

## ADRs

ADR-027, ADR-028, ADR-029. Decisions D027–D029.

## Phase 4.1 corrective (D030)

- Seed is a real control: `sha256_seeded_tiebreak_v1` only (no RNG).
- Canonical fingerprint shared by selection + replay.
- Evidence provenance for strongest QSQ-EVD (`observed` only).
- `quality_policy.py` genre split. No Phase 5. Freezes unchanged.
- No `query-set-v4` bump — additive `selection_seed_method` field only.
