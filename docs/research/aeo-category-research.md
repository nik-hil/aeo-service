# AEO Category Research

**Product context:** Greenfield Answer Engine Optimization (AEO) SaaS MVP — backend-only, Python, one public website at a time. Supports crawl, technical/content/entity/structured-data analysis, transparent AEO Health Score, recommendations, controlled AI visibility experiments, JSON API, SQLite, deterministic demo mode. Experiments must never claim to reproduce ChatGPT/Gemini/Perplexity ranking.

**Research window:** Category literature and product positioning reviewed for 2024–2026 (as of 18 Sep 2026 IST).

---

## Sources consulted (with URLs)

1. GrowthHasten — *AEO vs GEO: What the Difference Actually Changes* — https://growthhasten.com/blog/aeo-vs-geo (published/updated Aug 2026)
2. Similarweb — *AEO vs. GEO: What’s the Difference?* — https://aisearch.similarweb.com/blog/aeo-vs-geo/ (Feb 2026)
3. Trakkr — *AEO vs GEO: Differences, Overlap, and Which Term to Use* — https://trakkr.ai/guides/aeo-vs-geo (Aug 2026)
4. Aggarwal et al. — *GEO: Generative Engine Optimization* (arXiv / KDD 2024) — https://arxiv.org/pdf/2311.09735
5. Metehan Yesilyurt — *How AI Visibility Tools Actually Collect Data* — https://metehan.ai/articles/how-ai-visibility-tools-collect-data/ (Sep 2026)
6. GEO Optimizer — Features (crawl → schema → brand monitor workflow) — https://geooptimizer.ai/features
7. Semrush — *The 8 Best AI Visibility Tools to Win in AI Search (2026)* — https://www.semrush.com/blog/best-ai-visibility-tools/
8. KIME — *Best AI Visibility Tools in 2026* — https://kime.ai/blog/best-ai-visibility-tools
9. Am I Cited — *The 60-Point Technical AEO Audit Checklist* — https://www.amicited.com/blog/technical-aeo-audit-checklist-60-point/
10. Nick Lafferty — *AI Visibility Metrics: Formulas, Benchmarks & Sample Sizes (2026)* — https://nicklafferty.com/blog/ai-visibility-metrics-reference/
11. Supporting product/category pages (feature awareness only): Peekaboo https://www.aipeekaboo.com/ ; Indexly https://indexly.ai/indexly-visibility ; Siftly https://siftly.ai/features/ai-brand-monitoring ; Georion https://georion.app/features ; OptimizeGEO https://www.optimizegeo.ai/features

---

## Category definition (AEO / GEO / AI visibility)

### Working definitions (industry practice, not a standards body)

| Term | Typical meaning | Origin / notes |
| --- | --- | --- |
| **SEO** | Crawlability, indexability, rankings, clicks on classic SERPs | Foundation; still required |
| **AEO (Answer Engine Optimization)** | Make passages extractable for direct answers, snippets, voice, AI Overviews; page/passage-level | Industry coinage (~2017–2018); no single founding paper; definitions vary |
| **GEO (Generative Engine Optimization)** | Improve how a brand/source is retrieved, mentioned, cited, and synthesized inside generative answers | Formalized in Aggarwal et al., KDD 2024; GEO-bench |
| **AI visibility** | Outcome umbrella: whether/where/how a brand appears in AI answers | Clearest reporting label across engines |
| **LLMO / AI SEO / AIO** | Overlapping marketing labels for the same territory | Avoid as primary product language |

### Practical synthesis for our product

- **Commercial job is one:** improve whether a website/brand is findable, accurately described, cited, and recommended in AI-mediated answers — without pretending AEO and GEO are two separate products.
- **Useful diagnostic split** (GrowthHasten / Similarweb / Trakkr converge):
  1. **On-site extractability** — Can a passage be lifted and still answer a question? (structure, FAQ/HowTo shape, schema, entity clarity)
  2. **Off-site corroboration** — Do third-party sources describe the brand consistently enough to be named? (PR, directories, co-citations) — largely out of scope for a one-site MVP except as *recommendations*
- **Google-specific caveat:** Google Search Central states there are no special requirements / AI-only files / special schema *for Google AI features*; that guidance does **not** speak for ChatGPT, Perplexity, Claude, etc.
- **Our positioning:** Use **AEO** as the product category name (matches MVP brief), define scope as **site readiness for answer engines + controlled, disclosed AI visibility experiments**, and treat GEO/AI visibility as overlapping vocabulary users will search for.

---

## Common user workflow

Across visibility platforms (Semrush AI Toolkit, Otterly, Peec, Profound, Scrunch, Indexly, Peekaboo, GEO Optimizer, Georion, OptimizeGEO, etc.) the repeated operating loop is:

1. **Onboard a brand / site** — domain, competitors (often), markets/languages.
2. **Define prompt / question sets** — buyer questions, comparisons, category prompts (manual + suggested).
3. **Measure appearance** — run prompts across selected engines; record mentions, position, citations, sentiment.
4. **Diagnose gaps** — which prompts lost; which URLs/domains get cited instead; technical/content blockers.
5. **Fix readiness** — crawlability, bots, schema, answer-shaped content, entity consistency, freshness.
6. **Publish / distribute** — on-site updates + often third-party/PR (later-stage products).
7. **Re-measure & report** — share of voice trends, citation share, alerts; export for agencies/clients.

**Technical-audit-first subflow** (GEO Optimizer, Profound technical AEO, Am I Cited checklist):

URL(s) → crawl/render check → extract metadata/headings/JSON-LD → validate schema/entities → score readiness → recommend fixes → (optional) visibility monitor.

**Implication:** Category leaders sell *continuous multi-engine brand monitoring*. Our MVP is deliberately **site-first, analysis-first, experiment-second** — closer to an AEO readiness engine with honest, limited experiments than a full AI rank tracker.

---

## Jobs to be done

1. **Know if my site is even eligible** — Confirm bots can fetch HTML, pages aren’t blocked, content isn’t JS-only for AI crawlers.
2. **Understand why AI wouldn’t quote us** — Diagnose extractability, structure, schema, entity, and claim-clarity gaps on *our* pages.
3. **Get a single, explainable health number** — One score stakeholders can track, with transparent sub-scores (not a black box “74”).
4. **Prioritize what to fix next** — Rank recommendations by likely impact and effort for a small team.
5. **Run controlled visibility experiments** — Sample how models respond to fixed prompts *about* our site/category, with full methodology disclosure.
6. **Prove readiness / progress to a client or boss** — Machine-readable report (JSON) plus human-readable findings over time.
7. **Avoid false confidence** — Distinguish “our page is answer-ready” from “we rank in ChatGPT” (users expect honesty after being burned by vendor overclaim).
8. **Integrate into tooling** — JSON API so agencies/automation can pull scores and recommendations without a UI (fits backend-only MVP).

---

## MVP capabilities vs later

### MVP must-haves (aligned to brief + category JTBD)

| Capability | Why users expect it |
| --- | --- |
| Single public URL/site ingest + crawl | Entry point for every workflow |
| Technical analysis (HTTP, robots, canonicals, render/JS risk, AI bot directives) | Gate before any “optimization” advice |
| Content / extractability analysis (headings, answer-first blocks, FAQ/Q&A shape, claim density) | Core AEO page-level job |
| Entity analysis (consistent brand/product naming, Organization signals) | Models need clear “what is this” |
| Structured data analysis (JSON-LD presence, validity, type fit, `@id`/sameAs hygiene) | Explicit machine-readable facts |
| Transparent **AEO Health Score** with documented formula & component breakdown | Category markets scores; we differentiate with transparency |
| Prioritized recommendations (actionable, site-owned) | Users buy outcomes, not audits |
| Controlled AI visibility **experiments** (fixed prompts, logged runs, rates not ranks) | Category expectation — but scoped & caveated |
| Machine-readable report (JSON API) + SQLite persistence | Backend MVP / agency integration |
| Deterministic **demo mode** | Sales, CI, reproducible docs without live model spend |

### Nice-to-have / later

- Multi-engine continuous monitoring dashboards (ChatGPT, Gemini, Perplexity, Claude, Copilot, AI Overviews, AI Mode)
- Competitor share-of-voice / prompt labs at scale
- Sentiment & hallucination monitoring
- Auto schema generation / CMS one-click publish
- Content generation studios / agentic “fix it for me”
- Multi-site / multi-tenant agency workspaces
- GSC import, referral traffic attribution from AI domains
- Digital PR / citation outreach workflows
- Geo/language fan-out, shopping modules, multimodal assets
- Real UI scraping of consumer chat products (expensive; methodology-heavy)
- Claiming lift against live ChatGPT/Gemini/Perplexity “rankings”

### Explicitly out of MVP product claims

- Guaranteed inclusion in any AI answer
- Reproduction of proprietary engine ranking/retrieval
- Treating `llms.txt` as a proven citation booster (evidence as of mid-2026 is weak / contested; optional informational check only)

---

## Candidate flow evaluation + recommended flow

### Candidate (as given)

`URL → crawl → analyze → calculate AEO Health → AI visibility experiment → findings → prioritized recommendations → machine-readable report`

### Evaluation

| Step | Strength | Gap |
| --- | --- | --- |
| URL → crawl | Correct entry | Needs robots/bot/access gate + crawl budget/scope (one site) |
| analyze | Right pillars | Should be **explicit multi-analyzer** (technical / content / entity / structured-data) with stored evidence |
| AEO Health | Differentiator if transparent | Must compute **before** experiments so readiness ≠ visibility |
| AI visibility experiment | Expected by market | Placement after health is good; needs prompt set versioning, N runs, raw response storage, caveats |
| findings → recommendations | User value | Recommendations should merge **readiness findings + experiment observations**, prioritized once |
| machine-readable report | Fits backend MVP | Report should be the durable artifact of a **Job** with status lifecycle |

**Issues with the candidate as sequenced:**

1. “Findings” after experiment undersells crawl/analyze findings that exist *before* any model call.
2. No explicit **job lifecycle** (queued → crawling → analyzing → scoring → experimenting → complete) — needed for API/SQLite.
3. No **prompt-set / experiment config** step — experiments without a frozen prompt set are not comparable.
4. Demo mode needs a branch that skips live network/model I/O while preserving the same report schema.

### Recommended backend-first MVP workflow

```
1. create_job (URL, options, demo_mode?)
2. discover_and_crawl (respect robots; fetch HTML; store pages/assets metadata)
3. analyze_technical
4. analyze_content_extractability
5. analyze_entities
6. analyze_structured_data
7. compute_aeo_health (deterministic from analysis evidence + published formula version)
8. prepare_experiment (versioned prompt set; N runs; model/provider config OR demo fixtures)
9. run_visibility_experiment (store raw responses; compute rates with denominators)
10. synthesize_findings (merge readiness + experiment observations)
11. prioritize_recommendations
12. emit_report (JSON API artifact; persist in SQLite)
```

**Rationale**

- Matches category “measure → diagnose → fix → re-measure” without requiring continuous multi-engine SaaS.
- Keeps **health** grounded in *our crawl evidence* (auditable), separate from *stochastic experiments*.
- Puts experiment **after** readiness so users see: “you’re unreadable to bots” before “you weren’t mentioned in 3 sample prompts.”
- Supports deterministic demo by swapping steps 2 and 9 for fixtures while keeping steps 7, 10–12 identical.
- Aligns with research consensus that indexing/crawlability is the gate before AEO/GEO advice.

---

## AI visibility methodology caveats

Competitors and researchers market citations/mentions aggressively. Our product must respect these constraints in copy, API field names, and docs:

1. **Stochastic outputs** — Same prompt → different answers/citations across runs. Metrics are **sample estimates**, not census rankings (arXiv 2603.08924; Nick Lafferty 2026; Trakkr model-divergence ~43.9% average top-brand agreement across 8 systems).
2. **API ≠ consumer UI** — Developer APIs may use different models, disable web search, and miss citation UI modules (Metehan 2026). Never imply API experiments equal “what ChatGPT users see” unless UI-verified.
3. **No public ranking API** — Engines do not publish rank. Tools *generate* data by prompting. We must say **experiment / sample**, not **rank tracker for ChatGPT**.
4. **Sampling beats breadth theater** — Few prompts × many runs > many prompts × one run for stable rates.
5. **Report denominators** — Every rate needs prompts × runs × window; raw responses must be inspectable.
6. **Model updates break series** — Silent provider updates can move all brands; annotate config/model/version/time.
7. **Mention ≠ citation ≠ recommendation** — Separate fields; entity-normalize brand strings.
8. **Google vs other engines** — Google may say “no special AI optimizations”; other products have different retrieval. Don’t universalize one vendor’s guidance.
9. **No guaranteed outcomes** — “We get you into ChatGPT” is advertising, not measurement.
10. **llms.txt / magic files** — Contested signal; do not sell as citation silver bullet (multiple 2026 studies + Google guidance skepticism).

**Product language we should use:** visibility experiment, sample rate, observed mention/citation in run, confidence/uncertainty note, methodology version.

**Language we must avoid:** “ChatGPT ranking,” “reproduced Perplexity SERP,” “guaranteed citations,” “official AI share of voice” (unless we invent our own clearly labeled metric).

---

## Implications for our backend-first MVP

1. **Job-centric architecture** — Persist a Job with phased status; each analyzer writes Evidence rows; Health and Report are derived artifacts.
2. **Formula versioning** — Store `health_formula_version` and `experiment_protocol_version` on every report for reproducibility.
3. **Evidence-backed recommendations** — Every recommendation links to crawl/analysis evidence IDs (and optionally experiment observation IDs).
4. **Experiment module isolation** — Pluggable runner (live vs demo fixtures); never hard-code claims that live runners mirror consumer ChatGPT/Gemini/Perplexity ranking.
5. **SQLite schema for auditability** — pages, analysis_results, health_scores, prompts, experiment_runs, raw_responses, findings, recommendations, reports.
6. **JSON API as primary UX** — Report schema should be stable and self-describing (caveats object, methodology, score breakdown).
7. **Prioritize on-site readiness** — Technical/content/entity/schema deliver most of MVP value without expensive multi-engine monitoring.
8. **Honest defaults** — Small prompt sets, multiple runs, Wilson/cluster caveats in docs even if MVP only reports simple rates + N.
9. **One site at a time** — Simplify crawl graph, robots, and scoring; defer competitor graphs.
10. **Demo mode first-class** — Same report shape; seeded findings so CI and sales demos don’t need model keys.

---

## What NOT to copy

Do **not** clone competitors’ product surfaces, proprietary metric formulas, prompt libraries, UI layouts, or marketing claims. Specifically avoid:

| Do not copy | Why |
| --- | --- |
| Branded proprietary scores presented as industry standards (e.g. “Brand Visibility Score” as if universal) | Invent **our own** transparent AEO Health components with published weights |
| Multi-engine always-on monitoring as MVP centerpiece | Out of scope; expensive; methodology minefield |
| Guarantees of ChatGPT/Gemini/Perplexity inclusion or ranking | False and policy-violating for our brief |
| Undisclosed API scraping presented as “real ChatGPT results” | Integrity risk (Metehan red flags) |
| Competitor SOV leaderboards as the first screen | Requires multi-brand tracking we don’t have |
| Auto-generated “GEO schema” sold as secret sauce | Schema.org is public; we analyze/validate, don’t invent fake vocab |
| Overweighting `llms.txt` generators as core value | Weak citation evidence; optional check only |
| Content studios / one-click CMS publishing | Post-MVP |
| Agency multi-tenant workspaces, alerts Slack bots, PR outreach | Post-MVP |
| Any verbatim copy of competitor docs, checklists, or UI copy | Legal/ethical; synthesize needs into original product language |

**Copy the user jobs, not the products:** readiness diagnosis, transparent scoring, prioritized fixes, disclosed experiments, machine-readable proof.

---

## Appendix: Metric names commonly marketed (awareness only)

*We will invent our own transparent formulas; this list is for vocabulary awareness.*

- Brand Visibility Score / AI Visibility Score  
- Brand Mention Share / Mention Rate / Presence  
- Share of Voice (AI SOV)  
- Citation Rate / Citation Share / Cited URL rate  
- Prompt Coverage / Topical Coverage  
- Recommendation Position / Answer Position  
- Sentiment Distribution / Narrative score  
- Domain Influence / Authority-of-cited-sources  
- Hallucination / Accuracy flags  
- Snippet win rate / AI Overview appearance (AEO-leaning)  
- Zero-click impressions (search-adjacent)

**Our direction:** e.g. componentized AEO Health (Technical, Extractability, Entity, StructuredData) + separate Experiment Mention Rate / Citation Observation Rate with explicit N — names TBD by product, formulas published in-repo.

---

*End of report.*
