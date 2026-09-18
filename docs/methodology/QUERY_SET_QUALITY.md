# Query-set quality evaluation (`query-set-quality-v1` / `query-quality-v1`)

**Status:** Binding methodology (Phase 4)  
**Goal:** Representative, high-quality, non-redundant, **reproducible** query sets.  
**Not** score inflation. **Not** a website / AEO grade.

## Allowed diagnostics

Named, versioned panels. Independently inspectable. No opaque single score.

| ID | Measures |
| --- | --- |
| QSQ-SPEC | Specificity — not heading paste / brand fluff |
| QSQ-ANS | Answerability |
| QSQ-REL | Relevance to evidenced topics/entities |
| QSQ-ENT | Entity alignment (not platform apex) |
| QSQ-EVD | Evidence honesty (≥2 classes) |
| QSQ-DEDUP | Near-dup collapse after normalize |
| QSQ-DIV | Intent & topic stratum coverage vs genre policy |
| QSQ-LEAK | Industry/genre leak |
| QSQ-DET | Determinism fingerprint |
| QSQ-COV | Coverage judgment (themes from *this* snapshot) |

Per-candidate dimensions in code: relevance, specificity, answerability,
grammaticality_lint, entity_alignment, evidence_support, duplication,
intent_label_consistency, WEAK_INDUSTRY_LEAK.

## Forbidden

1. Overall website quality / AEO health-from-queries composite.  
2. Objectives that maximize appearance/citation by rewriting queries toward easy wins.  
3. Selection loops that reward “queries the model already cites.”  
4. Marketing that equates diagnostic pass rate with ranking.

## Determinism

Identical crawl/profile snapshot + seed + versions + top_k → identical ordered
`query_id` / `text` / fingerprint. Changing only seed may differ; both must pass floors.

## Coverage without niche hard-coding

Coverage themes are derived from SiteProfile evidence for **this** snapshot.
Fixtures may assert theme presence from their own evidence; production paths must
not special-case hostnames (e.g. `nik-hil.hashnode.dev`) or “AI blog” packs.

## Live protocol

Offline fixtures → dry-run replay PASS → freeze QuerySet → **then** optional paid run.
Discovery / dry-run must make **zero** paid DO calls.
