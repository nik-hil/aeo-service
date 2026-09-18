# Query-set quality evaluation (`query-set-quality-v1.1.1` / `query-quality-v1`)

**Status:** Binding methodology (Phase 4 + 4.1 + **4.1.1 provenance honesty**)  
**Code gate version (frozen):** `query-quality-v1`  
**Set methodology patch:** `query-set-quality-v1.1.1` (Phase 4.1.1; does **not** bump
frozen `query-quality-v1` / `query-set-v3`)  
**Goal:** Representative, high-quality, non-redundant, **reproducible** query sets.  
**Not** score inflation. **Not** a website / AEO grade.

Diagnostics ≠ website score. Query-set ≠ health-v1.

Verifier writes **new** `VERIFY-PHASE4.1.1-PROVENANCE-2026-09-18` — do **not**
overwrite `VERIFY-PHASE4.1-CORRECTIVE-2026-09-18.*`.

## Allowed diagnostics

Named, versioned panels. Independently inspectable. No opaque single score.

| ID | Measures |
| --- | --- |
| QSQ-SPEC | Specificity — not heading paste / brand fluff |
| QSQ-ANS | Answerability |
| QSQ-REL | Relevance to evidenced topics/entities |
| QSQ-ENT | Entity alignment (not platform apex) |
| QSQ-EVD | Evidence honesty — **≥2 distinct `observed` classes** (derived/compatibility do not count) |
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

## Phase 4.1.1 Evaluator gates (provenance honesty)

Binding: `docs/architecture/PHASE4_1_1_PROVENANCE_LOCK.md`.

| Gate | Assert intent | Blocks merge? |
| --- | --- | --- |
| **P1** | `normalize_provenance`: missing/unknown → **compatibility** (never silent observed) | **yes** |
| **P2** | No implicit observed — ban `setdefault(..., "observed")` / stamp-to-observed in adapters | **yes** |
| **P3** | QSQ-EVD ≥2 **distinct** `observed` classes only | **yes** |
| **P4** | Generator preserves explicit provenance; fills missing → compatibility | **yes** |
| **P5** | Missing/unknown regression → EVD **fail** | **yes** |
| **P6** | Arbitrary-site synthetic fixtures follow the same rules | no |
| **P7** | Freezes held (ssrf/target_site/domains/health/DO; versions; no query-set-v4) | no |
| **P8** | No paid DigitalOcean in discovery/dry-run | **yes** |

## Evidence provenance (Phase 4.1 / 4.1.1)

`EvidenceRecord.provenance`:

- `observed` — counts for strongest QSQ-EVD  
- `derived` — does not count (includes mapped SiteProfile heuristic/derived_metric/llm_assist)  
- `compatibility` — SiteUnderstanding legacy fillers / missing / unknown; does not count  

Examples: 2 distinct observed → pass; 1 observed + derived → fail strongest;
derived-only → fail; two same-class observed → fail (need ≥2 **distinct** classes).

`normalize_provenance` is the trust boundary (see
`PHASE4_1_1_PROVENANCE_LOCK.md`): heuristic/derived_metric/llm_assist → derived;
missing/unknown → compatibility; never invent `observed`. Crawl EvidenceRef
must stamp observed explicitly at construction only — never via adapter
setdefault / stamp-to-observed.

## Forbidden

1. Overall website quality / AEO health-from-queries composite.  
2. Objectives that maximize appearance/citation by rewriting queries toward easy wins.  
3. Selection loops that reward “queries the model already cites.”  
4. Marketing that equates diagnostic pass rate with ranking.
5. Silent promotion of missing/unknown evidence provenance to `observed`.

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
