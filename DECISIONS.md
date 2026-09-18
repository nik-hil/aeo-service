# DECISIONS.md — AEO MVP

Assumptions and decisions made without asking the user. Update when overturned.

## D001 — Build location (2026-09-18)
**Decision:** Develop and run the MVP on the Grok cloud computer (`/workspace/aeo-mvp`). Move to GitHub after the MVP is proven.
**Rationale:** User/profile require local runnable demo on the Grok computer; GitHub comes later. Cursor Origin/cloud-agent may be used later for polish if needed; primary source of truth for the MVP is this tree.
**Alternatives considered:** Immediate Origin `new_repo` cloud agent only — deferred because demo must run here first.

## D002 — Stack (2026-09-18)
**Decision:** FastAPI + Pydantic v2 + SQLAlchemy 2.x + SQLite + httpx + selectolax + pytest.
**Rationale:** Matches recommended tech; simple, maintainable, no distributed infra.

## D003 — Scope exclusions (2026-09-18)
**Decision:** No auth, billing, multi-tenancy, frontend, or production deploy in MVP.
**Rationale:** Explicit product scope.

## D004 — One site per analysis job (2026-09-18)
**Decision:** Each analysis run targets exactly one user-supplied public base URL; crawl depth/page caps are fixed and documented.
**Rationale:** MVP simplicity and demoability.

## D005 — AI visibility honesty (2026-09-18)
**Decision:** Experiments are *controlled observations* via pluggable providers (including a deterministic DemoProvider). Never claim reproduction of proprietary answer-engine ranking.
**Rationale:** Product requirement and category ethics.

## D006 — Demo mode (2026-09-18)
**Decision:** `AEO_DEMO_MODE=true` (or `provider=demo`) uses fixture crawl + synthetic visibility results with fixed seeds so scores and reports are bit-stable across runs.
**Rationale:** Demoable without API keys.

## D007 — LLM usage (2026-09-18)
**Decision:** Optional OpenAI-compatible LLM provider when `OPENAI_API_KEY` (or equivalent) is set; otherwise skip live LLM experiments and use demo/heuristic paths.
**Rationale:** Credentials may be unavailable; product must still work.

## D008 — Team model (2026-09-18)
**Decision:** Chief of Staff coordinates teammate agents: AEO Architect, AEO Researcher, AEO AI Evaluator, AEO Verifier. Verifier sign-off required before claiming a feature complete.
**Rationale:** Profile team structure.

## D009 — Backend workflow (CONFIRMED 2026-09-18)
**Decision:** Adopt the research-backed phased job flow:

`create_job → discover_and_crawl → analyze_technical → analyze_content_extractability → analyze_entities → analyze_structured_data → compute_aeo_health → prepare_experiment → run_visibility_experiment → synthesize_findings → prioritize_recommendations → emit_report`

**Status:** Confirmed. Supersedes the provisional candidate in the earlier D009 note.
**Rationale:** Category research (`docs/research/aeo-category-research.md`, `summary.json`) recommends multi-analyzer explicit steps, health **before** experiments (readiness ≠ visibility), versioned prompt prep, then merged findings → recommendations → report. Matches job lifecycle needs for API/SQLite and demo fixture swapping at crawl + visibility only.
**Alternatives considered:** Single “analyze” blob; experiment-before-health; continuous multi-engine monitoring as centerpiece — rejected for MVP honesty and scope.

## D010 — Package layout (2026-09-18)
**Decision:** Installable package name `aeo_mvp` lives under `src/aeo_mvp/` (src layout). Modules: `api`, `db`, `crawler`, `analyzers`, `scoring`, `visibility`, `recommendations`, `pipeline`, `report`, `demo`, `config`.
**Rationale:** Standard Python packaging; clear component boundaries in BLUEPRINT §5/§14.
**Alternatives considered:** Flat `aeo/` at repo root — rejected for import hygiene.

## D011 — API prefix (2026-09-18)
**Decision:** Versioned job API under `/api/v1` (`POST /jobs`, `GET /jobs/{id}`, `GET /jobs/{id}/report`, `GET /jobs/{id}/pages`). Liveness at `GET /health` without the version prefix.
**Rationale:** Leaves room for v2; health checks stay load-balancer friendly.
**Doc:** `docs/api/openapi-sketch.yaml`, BLUEPRINT §7.

## D012 — Crawl caps & politeness (2026-09-18)
**Decision:**
- Max **25** pages per job
- Max depth **2** (homepage = 0)
- **Same-host only** (registrable host match; no scheme-less external fan-out)
- Respect **robots.txt**
- Per-request timeout **5s**
- User-Agent: `AEOBot/0.1 (+research; respectful)`
**Rationale:** Bound runtime/storage for MVP; stay polite; align with D004.
**Overrides:** Request options may only tighten caps, not exceed maxima.

## D013 — Job status enum (2026-09-18)
**Decision:** `pending` → `crawling` → `analyzing` → `scoring` → `experimenting` → `synthesizing` → `completed` | `failed`.
**Rationale:** Maps 1:1 to pipeline phases for API polling and debugging.

## D014 — Health score weights philosophy (2026-09-18)
**Decision:** AEO Health (`health-v1`) is a weighted mean of Technical (0.25), Content (0.25), Entity (0.20), StructuredData (0.15), Answerability (0.15), each 0–100. Visibility experiment rates are **excluded** from Health.
**Rationale:** On-site readiness should be auditable from crawl evidence alone; weighting emphasizes technical+content gates first, then entity, then schema/answerability. Original formulas — not competitor clones. Changing weights requires a new `formula_version`.
**Doc:** `docs/methodology/METRICS.md`.

## D015 — Visibility protocol & providers (2026-09-18)
**Decision:** Protocol `vis-exp-v1`. Interface `AIVisibilityProvider` with `DemoProvider` (always) and `OpenAICompatibleProvider` (optional). Default prompt-set `prompt-set-v1` with 5 prompts × 3 runs. Store every observation (mention, citation, cited URLs, raw where permitted, methodology).
**Rationale:** Pluggable, honest, demoable; matches D005/D007.
**Doc:** `docs/methodology/AI_VISIBILITY.md`.

## D016 — Demo fixtures site (2026-09-18)
**Decision:** Deterministic fixtures under `src/aeo_mvp/demo/fixtures/` for fictional site `https://demo.example/` (never fetched live).
**Rationale:** Bit-stable demos and CI without network/model spend (D006).

## D017 — Recommendation priority (2026-09-18)
**Decision:** `priority_score = impact × effort_weight` with effort S/M/L → weights 1.0 / 0.7 / 0.4; every recommendation must link evidence/finding IDs; catalog `rec-catalog-v1`.
**Rationale:** Transparent prioritization for small teams; auditability.
**Doc:** `docs/methodology/RECOMMENDATIONS.md`.

## D018 — Blueprint authority (2026-09-18)
**Decision:** `docs/blueprint/BLUEPRINT.md` plus methodology siblings and OpenAPI sketch are the implementation source of truth until a later ADR overturns them.
**Rationale:** Architect deliverable for greenfield MVP; engineers implement without re-litigating scope.

## D019 — Experiment kinds (2026-09-18)
**Decision:** Split LLM mention experiments (`retrieval_enabled=false`) from AI search visibility experiments (`retrieval_enabled=true`). Rename non-retrieval metrics to `llm_*`. Never market chat-completions probes as AI-search visibility.
**Rationale:** External review P0; OpenAI-compatible chat has no web retrieval.

## D020 — SSRF hardening (2026-09-18)
**Decision:** All live crawler fetches go through `aeo_mvp.security.ssrf` validation (scheme, DNS, public IP, redirect revalidation, hop limit).
**Rationale:** External review P0 before any public deployment.

## D021 — Provider capability declarations (2026-09-18)
**Decision:** Every visibility provider exposes `ProviderCapabilities` including `retrieval_enabled` and `measures_consumer_ui=False` unless proven otherwise.
**Rationale:** Extensibility for future Perplexity/Gemini grounding without schema redesign.

## D022 — DigitalOcean web_search as first AI-search provider (2026-09-18)
**Decision:** Implement `DigitalOceanWebSearchProvider` against DigitalOcean Inference `POST /v1/responses` with `tools: [{type: web_search}]`. Auth via `DO_MODEL_ACCESS_KEY` (accept `MODEL_ACCESS_KEY` as docs fallback). Default model `openai-gpt-4o` (configurable `DO_INFERENCE_MODEL`). Protocol `ai-search-vis-v1`. `measures_consumer_ui=false`. Missing key / HTTP / absent web_search evidence → hard fail; never fabricate or silently degrade to LLM-only under `ai_search_visibility`. Emit `ai_search_*` / `target_domain_appearance_rate` metrics separately from `llm_*`. Registrable domains via Public Suffix List (`tldextract`). Live Hashnode retrieval validation is a follow-up on a machine with `DO_MODEL_ACCESS_KEY` (gated by `AEO_LIVE_RETRIEVAL_TEST=true`).
**Rationale:** First real retrieval-enabled visibility path without claiming consumer UI rankings; builds on D019/D021 abstractions.
**Doc:** `docs/methodology/AI_SEARCH_VISIBILITY_DO.md`.
**Alternatives considered:** Perplexity Sonar live path first (still stub); OpenAI Responses web_search (deferred); scraping consumer UIs (forbidden).

## D023 — Target site identity vs PSL (2026-09-18)
**Decision:** Keep `registrable_domain()` as true PSL eTLD+1 with
`include_psl_private_domains=True`. Introduce `TargetSiteIdentity` +
`target_match()` (`domain-match-v1`) for AI-search appeared/cited. Default
`match_scope=hostname` for supplemental multi-tenant platforms not on PSL
PRIVATE (`hashnode.dev`, `wordpress.com`, `medium.com`, `substack.com`,
`ghost.io`, `tumblr.com`). Ordinary sites default to `registrable_domain`
scope. www: strip one leading `www.` for compare only. Ban naive endswith.
Competitors use the same `site_key()`; omit target via `target_match`; do not
aggregate hosted tenants to platform apex. LLM-mention and health-v1 unchanged.
**Rationale:** Phase 2 Hashnode run incorrectly credited `hashnode.dev` /
sibling pubs when matching on PSL alone. True PSL of `nik-hil.hashnode.dev`
**is** `hashnode.dev` (not a bug to “fix”); product isolation is hostname
scope + supplemental allowlist. Private PSL fixes `alice.github.io` →
`alice.github.io`.
**Doc:** `docs/methodology/DOMAIN_MATCHING.md`, `AI_SEARCH_VISIBILITY_DO.md`.
**Alternatives considered:** Rewriting PSL to treat `nik-hil.hashnode.dev` as
eTLD+1 — rejected (false PSL). Using label-count alone for multi-tenant —
rejected. Suffix/endswith host match — rejected (lookalike hazard).

## D024 — Structured SiteProfile (Phase 3) (2026-09-18)
**Decision:** Wrap every assertive site-understanding field in `SiteProfileField`
(confidence ≤ 0.40 for heuristics, provenance, evidence refs). Split `site_genre`
from `industry_category`; industry defaults to omit unless strong-vote thresholds
(≥3, lead ≥2, ≥2 evidence classes). Bare `roadmap`/`kanban` never assert
`project_management`. Tags → topics only. Method `deterministic_html_v1+site-profile-v1`.
**Rationale:** Hashnode chrome “roadmap” bleed misclassified the publication as PM.
**Doc:** ADR-024, `docs/architecture/PHASE3_QUERY_DISCOVERY.md`.

## D025 — Query discovery v1 / query-set-v2 (2026-09-18)
**Decision:** Pipeline generate 30–50 → normalize/dedupe → diagnostic gate →
select ~20 with deterministic seed. Intents:
informational|problem_solving|comparison|recommendation|navigational|commercial.
Genre-gated templates. Gate includes `WEAK_INDUSTRY_LEAK`. No new opaque AEO score.
**Rationale:** Stop industry-leak query templates; make sets reproducible and explainable.
**Doc:** ADR-025, `docs/methodology/QUERY_DISCOVERY.md`.

## D026 — Paid retrieval opt-in (2026-09-18)
**Decision:** Never auto-run DO `web_search` from discovery. Require ready
`QuerySet` + explicit `paid_retrieval_opt_in` / `AEO_PAID_RETRIEVAL_OPT_IN`.
**Rationale:** Cost control; discovery quality independent of paid retrieval.
**Doc:** ADR-026.

## D027 — Query discovery v2 / query-set-v3 (2026-09-18)
**Decision:** Default pipeline `query-discovery-v2` → `query-quality-v1` →
coverage/MMR selection → `query-set-v3`. Keep `query-discovery-v1` selectable.
Seed aliases `selection_seed`|`query_selection_seed`|`experiment_seed` with
persisted `root_seed`/`effective_seed`. Persist full candidates + rejected.
**Rationale:** Fix Phase 3 seed/gate/diversity defects; generic ANY-site generation.
**Doc:** ADR-027, `docs/architecture/PHASE4_QUERY_INTELLIGENCE.md`.

## D028 — Query quality diagnostics ≠ site grade (2026-09-18)
**Decision:** `query-quality-v1` decomposable pass/warn/fail dimensions including
grammaticality lint. Set-level QSQ-* panels. Forbidden: opaque AEO/site score;
folding diagnostics into `health-v1`.
**Rationale:** Measurement integrity; reject title-wrap garbage without gaming Health.
**Doc:** ADR-028, `docs/methodology/QUERY_SET_QUALITY.md`.

## D029 — Intent budgets + dry-run reproducibility (2026-09-18)
**Decision:** `intent-budget-v1` hard min/max; MMR λ≈0.65; max-per-topic caps;
`discovery_only`/`dry_run` with fingerprint replay and zero paid calls.
**Rationale:** Stop PS/topic monopoly; require offline replay before paid live.
**Doc:** ADR-029.

## D030 — Phase 4.1 seed tie-break + evidence provenance (2026-09-18)
**Decision:** Corrective only (no Phase 5). Architect binding: primary selection
path is seed-independent (budgets → coverage → MMR → confidence → query_id);
seed used **only on ties** via `selection_seed_method=sha256_seeded_tiebreak_v1`
=`sha256(f"{effective_seed}|{query_id}").hexdigest()` — never PRNG/shuffle.
Canonical fingerprint preimage = ordered members
`(query_id,text,intent,topic,entity)` + audit (method/versions/seed/top_k/dedup);
shared by selection + replay; excludes frozen_at/unstable ids.
`EvidenceRecord.provenance` ∈ observed|derived|compatibility; only **observed**
counts for strongest QSQ-EVD. Genre policies in `quality_policy.py`.
Kept `query-set-v3` (additive fields; no v4).
**Rationale:** Phase 4 persisted seeds but ignored them; fingerprint/evidence gaps.
**Doc:** `docs/methodology/QUERY_DISCOVERY.md`, `QUERY_SET_QUALITY.md`.

## D031 — Phase 4.1.1 evidence provenance trust boundary (2026-09-18)
**Decision:** Corrective only (no Phase 5). `normalize_provenance(raw)` →
observed|derived|compatibility; missing/unknown → compatibility. Never promote
missing/unknown to observed in generate_v2 / adapters. Preserve explicit values.
Crawl `EvidenceRef` stamps observed at construction (hard contract); field origin
≠ evidence provenance. QSQ-EVD unchanged: ≥2 distinct observed classes.
Kept `query-set-v3` / `query-discovery-v2` (no version bump).
**Rationale:** generate_v2 previously manufactured observed from unstructured
SiteProfile evidence lacking provenance, inconsistent with EvidenceRecord.from_dict.
**Doc:** `docs/methodology/QUERY_DISCOVERY.md`.
