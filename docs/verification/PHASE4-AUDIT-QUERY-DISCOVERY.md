# Phase 4 readiness audit — Query discovery / SiteProfile

**Audit type:** Read-only (no product code changes)  
**Repo:** `nik-hil/aeo-service`  
**Audited commit:** `dc1b963a3f74f9debe81318d325e746ab7642d05` (docs: live Phase 3 verify)  
**Phase 3 impl:** `7ac08ef102eb34f9998c8078155fe7072e87c18b`  
**Live job cross-check:** `970aefc3-7d5a-4465-b0a8-79cb3e885458` (`docs/verification/LIVE_PHASE3_HASHNODE_2026-09-18.json` + uploaded verify artifacts)  
**Pytest (this audit):** **107 passed, 1 skipped, 0 failed** (108 collected; skip = `test_live_digitalocean_web_search_optional`)  
**Date:** 2026-09-18

**Overall readiness:** Phase 3 gates PASS for Hashnode, but **not yet Phase-4-ready** as a generic query-discovery product. Core gaps: template/AI-agent overfit, weak quality gate (live 0 rejects), seed/API contract mismatch, intent mix only partially controlled, poor topic hygiene / semantic diversity.

---

## Inventory (code map)

| Area | Path | Role |
| --- | --- | --- |
| SiteProfile schema | `src/aeo_mvp/understanding/profile.py` | `SiteProfileField`, evidence classes, `QUERY_DISCOVERY_METHOD` |
| Profile builder | `src/aeo_mvp/understanding/builder.py` | Evidence-first genre/industry; Hashnode chrome strip |
| Legacy projection | `src/aeo_mvp/understanding/site.py` | `SiteUnderstanding` + DB `site_profiles.profile_json` |
| Generate | `src/aeo_mvp/queries/generate.py` | Templates → 30–50 `CandidateQuery` |
| Normalize/dedup | `src/aeo_mvp/queries/normalize.py` | NFKC + Jaccard≥0.85; one-per `(topic,intent)` |
| Gate | `src/aeo_mvp/queries/gate.py` | Diagnostic accept/reject dims + `WEAK_INDUSTRY_LEAK` |
| Select | `src/aeo_mvp/queries/select.py` | Stratified `query-set-v2`; `_seed_from` |
| Orchestration | `src/aeo_mvp/queries/discovery.py` | generate→dedupe→gate→select → `DiscoveryResult` |
| Persist helpers | `src/aeo_mvp/queries/store.py` | `query_set_summary` |
| Pipeline wiring | `src/aeo_mvp/pipeline/orchestrator.py` | discovery → prompts → observations |
| Persist | `ExperimentConfig.discovered_queries_json`, `prompts_json`; report embeds `discovered_queries` |
| Methodology | `docs/methodology/QUERY_DISCOVERY.md`, ADR-024/025/026 |
| Tests | `tests/unit/test_query_discovery_v2.py` (8), `test_site_profile.py` (6), plus legacy `test_query_discovery.py` / `test_site_understanding.py` |

### Persisted `discovered_queries` / `query_set` shape

From `DiscoveryResult.to_dict()` + `QuerySet.to_dict()`:

- Top-level: `method`, `provenance`, `fallback_used`, `candidates_count`, `selected_count`, `accepted_count`, `rejected_count`, `queries[]`, `query_set{}`, `rejected_examples[]`, `intent_breakdown`, `paid_retrieval_opt_in`, `paid_retrieval_ready`, `discovery_method`, `query_set_version`
- Each selected query (legacy): `id`, `query`, `classification`, `intent`, `source`, `score`, `topic`, `entity`, `rationale`, `query_version`, `source_evidence`
- `query_set`: `query_set_id`, `query_set_version` (`query-set-v2`), `selection_seed`, `selection_method` (`stratified_intent_topic_v1`), `status`, `members[]` (rank + full candidate + gate), counts, `profile_snapshot`, `target_site_audit`, `warnings`, `frozen_at`, `evidence_hash`, intent/topic/entity breakdowns, paid flags

No separate DB table — JSON blob on experiment config + report.

### Intent assignment

Intent is **template-assigned at generation time**, not classified from free text:

- Navigational / informational / problem_solving / recommendation / comparison / commercial branches in `generate.py`
- Legacy map in `discovery.py` (`problem_solving`→`problem_solution`, `recommendation`→`best_for`, `navigational`→`brand`)
- `PERSONAL_BLOG_TARGETS` ratios are documented guidance only — **not enforced** in generation volume

### Flow into AI-search observations

1. `discover_queries` → `DiscoveryResult.as_prompts()` (`id`, `query`, `intent`)
2. Orchestrator `_build_prompts` → `prompt_set_id=discovered-queries-v1` (non-demo)
3. Each prompt run via provider (`digitalocean_web_search` when retrieval-enabled)
4. Rows in `visibility_observations` keyed by `query` / `prompt_id`
5. Metrics: appearance/citation under `domain-match-v1` (unchanged freeze)

---

## A. Is query generation genuinely generic?

**Verdict: Partially generic scaffolding; Hashnode/AI-agent overfit in practice.**

**Generic / genre-gated (good):**

- Genre branch `personal_tech_blog` vs SaaS (`generate.py` ~206–440): forbids cost/alternatives/products templates for blogs.
- Topics come from site evidence (`_topic_phrases`); brand from org evidence.
- ≥2 evidence classes required to seed (`_has_min_evidence` / per-`add` check).

**Overfit / non-generic (blocking for Phase 4 generality):**

| Evidence | Location |
| --- | --- |
| `_ai_topics()` regex prefers `ai|agent|llm|tool|python|harness|coding|filesystem|provider` for personal blogs | `generate.py:137–141`, used at 244, 285, 330, 359 |
| Hardcoded AI-agent query pack when any topic matches `\bagent\b` (tool calling, agent loop, filesystem tools, provider-agnostic) | `generate.py:310–327` |
| Hardcoded recommendation: `Is {brand} a good resource for AI agents?` for every personal blog | `generate.py:345–355` |
| Builder `TOPIC_AI_HINTS` + industry `ai_ml` strong patterns tuned to agent/LLM language | `builder.py:88–108` |
| Hashnode-specific chrome regex (`powered by hashnode`, tag/series paths) | `builder.py:68–75` — defensive, but platform-specialized |

Live selected set is almost entirely AI-agent / permissions series language (see H). A non-AI personal blog would still hit the “AI agents” recommendation if genre=`personal_tech_blog` and brand exists — **genre alone triggers AI wording**.

---

## B. Is query quality filtering genuinely generic?

**Verdict: Gate mechanism is generic; live filtering is weak / mostly inert.**

Dimensions (`gate.py`): relevance, specificity, answerability, entity_alignment, evidence_support, duplication, `WEAK_INDUSTRY_LEAK`.

**Generic:** PM/SaaS leak regexes; personal-blog forbidden commercial templates; evidence-class count; near-dup vs accepted set.

**Weak / not quality-as-product:**

- Live Hashnode: `accepted_count=29`, `rejected_count=0`, `rejected_examples=[]` — **gate rejected nothing**.
- Accepts mangled templates: e.g. live selected  
  `How does Why does an AI agent need permissions compare to other approaches?`  
  `Key concepts in Nikhil Ikhar's blog`  
  `Common pitfalls when working with Nikhil Ikhar's blog`
- Relevance can **warn** and still accept (`accept_with_warning`); no score threshold beyond fail dims.
- Specificity only checks token length / a tiny vague set — does not reject title-stuffed or double-question text.
- Tests prove leak rejection (`test_weak_industry_leak_rejected`) but not linguistic quality.

So filtering is **generic anti-leak diagnostics**, not a genuine quality filter that would drop bad candidates.

---

## C. Is query selection deterministic?

**Verdict: Yes, given fixed candidates + seed + evidence_hash.**

- `select_query_set` uses `random.Random(seed)` then sort; Python’s stable sort preserves seed-driven order **among equal confidence** (`select.py:185–193`).
- Tie-breaks: `-confidence`, then `query_id` (stable hash of intent|text|version).
- `test_deterministic_selection_seed_reproducible` asserts identical lists for `selection_seed=42` twice.
- Caveat: `frozen_at` uses `datetime.now()` — wall-clock, not bit-identical across runs (cosmetic).

---

## D. Is the current seed reproducible end-to-end?

**Verdict: Deterministic for a fixed understanding snapshot; not fully reproducible as an operator-controlled “seed=42” job.**

| Layer | Reproducible? | Notes |
| --- | --- | --- |
| Same `SiteUnderstanding` + explicit seed | Yes | Unit-tested |
| Same `evidence_hash`, no explicit seed | Yes | Derived seed from hash |
| Live crawl → same pages/order | Partial | Crawl set/order can change `topics` / hash |
| Operator `selection_seed` via API | **No (broken contract)** | See E |
| `JobOptions` schema | Missing | No `query_selection_seed` / `paid_retrieval_opt_in` fields (`api/schemas.py`) — extras dropped on API create |
| Dry-run replay | Missing | No first-class replay of frozen candidate pool |

Paid path: discovery itself does not call DO; observations require opt-in + ready set (ADR-026). Replaying visibility still needs provider + opt-in.

---

## E. `options.selection_seed=42` vs `query_set.selection_seed=11607312`

**Verdict: Intentional hash-derived seed when no explicit seed reaches `select_query_set`. The “42 vs 11607312” gap is a reproducibility / naming defect (or verifier conflation), not a designed dual-seed.**

### Trace of `11607312`

Live artifact:

- `site_understanding.evidence_hash` = `0474cd7f96d66bba`
- `query_set.selection_seed` = `11607312`

Code (`select.py:_seed_from`):

```python
if explicit is not None:
    return int(explicit)
raw = evidence_hash or "default"
return int(hashlib.sha256(raw.encode()).hexdigest()[:8], 16)
```

Independent check:

```text
sha256("0474cd7f96d66bba").hexdigest()[:8] → int(..., 16) = 11607312
```

Exact match → **live job used derived seed** (`explicit is None`).

### Trace of “42”

- Orchestrator wires: `selection_seed=options.get("query_selection_seed")`  
  (`orchestrator.py:267`) — **not** `selection_seed`.
- LIVE summary JSON does **not** contain `selection_seed: 42` or `query_selection_seed`.
- Unit/offline verify convention uses `selection_seed=42` (`test_query_discovery_v2.py`, VERIFY-PHASE3 doc).
- Verify-live limitation text claims `options.selection_seed=42` (DB may have had a wrong-keyed field; artifact dump does not include `options_json`).

**If** job options contained `selection_seed: 42` (wrong key), orchestrator would ignore it and derive `11607312`.  
**If** options had `query_selection_seed: 42`, `query_set.selection_seed` would be `42` (`_seed_from(hash, 42)` returns 42) — contradicted by artifact.

**Conclusion:** Live effective seed was **evidence-hash-derived `11607312`**. Persisting both a human “42” expectation and a derived seed without documenting `root_seed` vs `effective_seed` is a **Phase 4 defect** to fix in query-set-vN (single root seed, explicit derivation record).

---

## F. Is 29→20 a quality filter or merely selection?

**Verdict: Merely selection (plus pre-gate near-dedupe). Not quality filtering.**

Live counters (`LIVE_PHASE3` / verify JSON):

| Metric | Value |
| --- | --- |
| `candidates_count` | 29 |
| `accepted_count` | 29 |
| `rejected_count` | 0 |
| `selected_count` | 20 |

Pipeline: generate → `dedupe_by_text` → gate (0 rejects) → `select_query_set(top_k=20)`.

Also: advertised generate band is 30–50; live produced **29** (below `min_candidates=30`) — padding exhausted topics / evidence. Offline fixtures produced 40→20 with 0 rejects as well.

---

## G. Is intent/category distribution controlled or accidental?

**Verdict: Partially controlled, then fill-dominated (accidental skew).**

**Controlled:**

- Round-robin over `STRATA_ORDER` (`select.py:199–229`) prefers one-per-intent cycle and new topics.
- Commercial capped for `personal_tech_blog`.
- Documented personal-blog mix in methodology (not hard quotas).

**Accidental / fill:**

- Live selected: informational **4**, problem_solving **8**, recommendation **4**, comparison **3**, navigational **1**.
- Navigational pool tiny (brand templates) → strata exhausts early → **Pass 2** fills by confidence (`select.py:231–238`) → problem_solving surplus.
- `PERSONAL_BLOG_TARGETS` never applied as generation quotas.
- Industry/category does not drive selection strata (only genre commercial cap + generation branches).

---

## H. Are queries diverse enough (topic / intent / entity / journey)?

**Verdict: Insufficient for a serious visibility panel.**

Live `topic_breakdown` / selected list:

- Entity: **100%** `Nikhil Ikhar's blog` (`entity_breakdown`).
- Topics heavily clustered on 3 near-duplicate article titles (permissions / Agents #6 / “Why does…”) with 4 members each.
- Hardcoded agent pack adds diversity of *phrasing* but not of *site topical breadth* (Golang, System Design, MLOps in homepage description unused).
- Funnel: almost all awareness/consideration; no real decision journey beyond soft templates.
- User-journey diversity: weak — many “What is {full H1}?” / “How does {full H1} work?” clones.
- Chrome-ish legacy topics still on understanding list: `Comments (1)`, `More from this blog`, numbered TOC headings — can seed padding junk (`Key concepts in Nikhil Ikhar's blog`).

Intent labels are diverse enough on paper; **semantic diversity is not**.

---

## I. Logic overfit to Hashnode / AI-ML / blogs / agents / nikhil’s site?

**Verdict: Yes — material overfit beyond legitimate genre gating.**

| Kind | Example | Severity |
| --- | --- | --- |
| Content pack | Hardcoded AI-agent how-to queries | High |
| Genre+AI wording | “good resource for **AI agents**” for any personal_tech_blog | High |
| Topic prior | `_ai_topics` / `TOPIC_AI_HINTS` | Medium–High |
| Platform chrome | Hashnode-named chrome/path regexes | Medium (defensive) |
| Test/fixture gravity | Hashnode fixtures dominate Phase 3 tests | Medium (coverage bias) |
| Genre gate → ai_ml remap | Personal blog SaaS override prefers ai_ml | Medium (may be correct for this site, brittle elsewhere) |

Legitimate (keep): supplemental multi-tenant Hashnode hostname scope (`domain-match-v1`) — **out of scope / frozen**, not query-discovery overfit.

---

## SiteProfile + evidence / provenance (inventory notes)

- Assertive fields wrapped with confidence ≤0.40, provenance, `evidence[]` (`profile.py`).
- Industry omit-by-default with strong-vote thresholds; weak `roadmap`/`kanban` alone cannot assert PM (verified offline + live `ai_ml` with title_h1/article_body).
- Live: `site_genre=personal_tech_blog`, `industry_category_guess=ai_ml`, `llm_used=false`, method `deterministic_html_v1+site-profile-v1`.
- Residual risk (from prior verify): chrome text can still appear under `article_body` evidence snippets; outcome correct but hygiene incomplete.
- Query provenance: `source_evidence` + `rationale` + `evidence_classes` on candidates; gate reasons on members.

---

## Test suite (this audit)

```text
python3 -m pytest tests/ -q --tb=line
→ 107 passed, 1 skipped, 0 failed
```

Discovery-focused:

- `tests/unit/test_query_discovery_v2.py` — normalize, intents, leak reject, seed, evidence, paid opt-in, Hashnode offline pipeline, legacy dedupe
- `tests/unit/test_site_profile.py` — Hashnode≠PM, evidence, unrelated category, Acme PM, confidence cap, omit industry
- Legacy: `test_query_discovery.py`, `test_site_understanding.py`

**Gaps in tests for Phase 4:** no multi-genre corpus (ecommerce, docs, non-AI blog); no assert on `query_selection_seed` API wiring; no replay/dry-run; no semantic diversity metrics; no rejection of title-stuffed / double-question queries; no enforcement of intent quotas.

---

## Gaps for Phase 4

1. **Remove / generalize AI-agent hardcodes** — evidence-conditioned phrase extraction, not fixed packs.
2. **Single root seed contract** — API `root_seed` → record `effective_selection_seed` + derivation formula; fix `query_selection_seed` vs `selection_seed` naming; expose on `JobOptions`.
3. **Versioned quality diagnostics** — reject title stuffing, double interrogatives, brand-as-topic padding; persist full candidate ledger (accepted+rejected), not only 10 reject examples.
4. **Coverage selection** — hard intent/topic/entity quotas; min distinct topic clusters; journey stages.
5. **Semantic dedup without paid embeddings** — char/token shingles, MinHash/LSH, or cheap local hash embeddings; raise beyond Jaccard 0.85 on bag-of-words.
6. **Topic hygiene** — strip chrome/TOC/comment headings before generation.
7. **Dry-run replay** — freeze candidate pool + seed → identical QuerySet offline.
8. **Candidate volume SLA** — explain when &lt;30; don’t silently undershoot.
9. **Broader fixtures** — non-Hashnode, non-AI sites in CI.
10. Keep freezes: SSRF, domain-match-v1, health-v1, LLM-mention vs AI-search semantics, DO provider boundaries.

---

## Recommended architecture — `query-discovery-v2` / `query-set-vN`

```
SiteProfile (unchanged freeze surface)
  → TopicNormalizer (chrome strip, phrase canonicalize)
  → CandidateGenerator v2 (genre kits; NO site-specific packs;
       phrases only from evidence spans)
  → QualityDiagnostics v1 (versioned codes; accept|reject|warn)
  → LexicalSemanticDedup (exact → Jaccard → MinHash bands;
       optional local embedding later, never required)
  → CoverageSelector v1 (quota matrix: intent × topic_cluster × funnel;
       deterministic under root_seed)
  → QuerySet v3 {
        root_seed, effective_selection_seed, derivation,
        diagnostics_version, coverage_report,
        full_candidate_ledger_ref, members[], frozen_at? optional
     }
  → DryRunReplay(ledger, root_seed) → bit-stable members
  → Paid retrieval gate unchanged (opt-in ∧ ready)
```

**Seeding:** One operator `root_seed` (default hash(evidence_hash|job_id|protocol)). Always persist both root and effective. Never accept undocumented alias keys.

**Diagnostics versioning:** e.g. `query-quality-diag-v1` with stable reason codes (`TITLE_STUFFING`, `DOUBLE_QUESTION`, `CHROME_TOPIC`, `WEAK_INDUSTRY_LEAK`, …) for longitudinal compare.

**Coverage:** Target bands become enforceable floors/ceilings; leftover slots filled by coverage deficit, not raw confidence dump.

---

## Risks

| Risk | Impact |
| --- | --- |
| Shipping Phase 4 metrics on current QuerySets | Visibility rates reflect agent-blog template quirks, not market queries |
| Seed/API mismatch | Operators believe seed=42; experiments silently hash-derived |
| Gate always-accept | Bad queries burn paid DO runs |
| Overfit packs | False confidence that discovery “works” beyond nik-hil.hashnode.dev |
| Intent fill skew | Overweights problem_solving How-to; underweights navigational/commercial where relevant |
| Topic chrome bleed | Nonsense queries (`pitfalls when working with {blog name}`) |
| No candidate ledger | Cannot audit 29→20 composition beyond selected 20 |

---

## Freeze confirmation (spot-check only; no product edits)

- `security/ssrf.py`, `target_site.py` / `domain-match-v1`, `scoring/health.py` WEIGHTS, AI-search vs LLM-mention split — not modified by this audit; live job remained `ai_search_visibility` + hostname match.

---

## Answers cheat-sheet

| Q | Answer |
| --- | --- |
| A Generation generic? | **No** — genre framework yes; AI/agent hardcodes + priors no |
| B Quality filter generic? | **Mechanism yes; effect weak** — live 0 rejects |
| C Selection deterministic? | **Yes** (fixed inputs) |
| D Seed E2E reproducible? | **Partial** — hash path yes; operator seed/API no |
| E 42 vs 11607312? | **Derived from evidence_hash**; 42 did not apply (`query_selection_seed` / missing options) |
| F 29→20? | **Selection only** (gate accepted all 29) |
| G Intent distribution? | **Partial control + confidence fill** |
| H Diverse enough? | **No** |
| I Overfit? | **Yes** (agents/AI/blog/Hashnode gravity) |

**Phase 4 entry criteria (suggested):** generic generator without hardcoded agent pack; root-seed contract tested via API; quality diag rejects live-class junk; coverage quotas met on ≥3 site genres; dry-run replay test green; full suite still ≥107 pass with freezes intact.
