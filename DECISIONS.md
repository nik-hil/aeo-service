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
