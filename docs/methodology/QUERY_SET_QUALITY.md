# Query-set quality evaluation (`query-set-quality-v1` / `query-quality-v1`)

**Status:** Binding methodology (Phase 4 + 4.1)  
**Goal:** Representative, high-quality, non-redundant, **reproducible** query sets.  
**Not** score inflation. **Not** a website / AEO grade.

Diagnostics ≠ website score. Query-set ≠ health-v1.

## Allowed diagnostics

Named, versioned panels. Independently inspectable. No opaque single score.

| ID | Measures |
| --- | --- |
| QSQ-SPEC | Specificity — not heading paste / brand fluff |
| QSQ-ANS | Answerability |
| QSQ-REL | Relevance to evidenced topics/entities |
| QSQ-ENT | Entity alignment (not platform apex) |
| QSQ-EVD | Evidence honesty — **≥2 `observed` classes** (derived/compatibility do not count) |
| QSQ-DEDUP | Near-dup collapse after normalize |
| QSQ-DIV | Intent & topic stratum coverage vs genre policy |
| QSQ-LEAK | Industry/genre leak (`quality_policy.py`) |
| QSQ-DET | Determinism fingerprint |
| QSQ-COV | Coverage judgment (themes from *this* snapshot) |

Per-candidate dimensions in code: relevance, specificity, answerability,
grammaticality_lint, entity_alignment, evidence_support, duplication,
intent_label_consistency, WEAK_INDUSTRY_LEAK.

Genre policies (`personal_tech_blog`, `saas_product`, `ecommerce`,
`documentation`, `default`) live in `quality_policy.py`; generic dims stay in
`quality.py`. Personal tech blog commercial/PM leak protections remain.

## Evidence provenance (Phase 4.1)

`EvidenceRecord.provenance`:

- `observed` — counts for strongest QSQ-EVD  
- `derived` — does not count  
- `compatibility` — SiteUnderstanding legacy fillers; does not count  

Examples: 2 observed → pass; 1 observed + derived → not 2 (fail strongest);
derived-only → fail.

## Forbidden

1. Overall website quality / AEO health-from-queries composite.  
2. Objectives that maximize appearance/citation by rewriting queries toward easy wins.  
3. Selection loops that reward “queries the model already cites.”  
4. Marketing that equates diagnostic pass rate with ranking.

## Determinism / seeds

Identical crawl/profile snapshot + seed + versions + top_k → identical ordered
`query_id` / `text` / fingerprint (`sha256_seeded_tiebreak_v1`).

- Same seed → same ordered set.  
- Different seeds **MAY** differ when alternatives exist.  
- Seed change ≠ site quality delta.  
- Seed is a real selection control (tie-break only); never bypasses quality gates.

## Coverage without niche hard-coding

Coverage themes are derived from SiteProfile evidence for **this** snapshot.
Fixtures may assert theme presence from their own evidence; production paths must
not special-case hostnames (e.g. `nik-hil.hashnode.dev`) or “AI blog” packs.

## Live protocol

Offline fixtures → dry-run replay PASS → freeze QuerySet → **then** optional paid run.
Discovery / dry-run must make **zero** paid DO calls.
