# Signal Classification — health-v1

**Date:** 2026-09-18 (IST)  
**Scope:** Classifies every health-v1 check / related product signal.  
**Immutability:** `health-v1` formulas and weights are **immutable**. Material methodology changes require a new `formula_version` (e.g. `health-v2`).

## Classes

| Class | Meaning |
| --- | --- |
| **observable** | Directly measured from crawl/fetch artifacts (HTTP status, robots bytes, HTML presence). |
| **derived** | Computed from observables via documented heuristics (scores, ratios, consistency). |
| **experimental** | Sample estimates from controlled visibility experiments; not rankings. |
| **industry_recommendation** | Aligns with common publisher/SEO/AEO guidance; not a causal proof. |
| **hypothesis** | Plausible AEO mechanism without strong public causal evidence; treat cautiously. |

## health-v1 component checks

| ID | Signal | Class | Notes |
| --- | --- | --- | --- |
| T1 | Homepage HTTP 200/203 | observable | Status code from fetch |
| T2 | robots allow for AEOBot `/` | observable | Parsed robots.txt |
| T3 | Homepage no `noindex` | observable | robots meta |
| T4 | Same-host canonical | observable / derived | Presence + host match |
| T5 | Title length band | derived | Length heuristic 15–70 |
| T6 | Meta description band | derived | Length heuristic 50–160 |
| T7 | JS-risk heuristic | derived | Script-byte ratio + body length |
| T8 | 2xx page share | derived | Ratio of crawl outcomes |
| C1 | Heading hierarchy | derived | DOM heading structure rules |
| C2 | Answer-first paragraph | derived | Early declarative block heuristic |
| C3 | FAQ/Q&A shape | derived | Heading/paragraph or FAQPage credit |
| C4 | Usable paragraph count | derived | `<p>` word-band counts |
| C5 | Visible word count band | derived | Text extraction heuristic |
| E1 | Brand token consistency | derived | Title/og/host candidate frequency |
| E2 | Organization signal | derived | JSON-LD or footer identity |
| E3 | Contact / sameAs | observable / derived | Links / schema fields |
| E4 | Brand ambiguity penalty | derived | Edit-distance divergence |
| S1 | Homepage JSON-LD parseable | observable | Parse success |
| S2 | JSON-LD page coverage | derived | Share of 2xx pages |
| S3 | Type-fit well-known types | derived | Presence of known `@type`s |
| S4 | `@type` hygiene | derived | Fraction of nodes with `@type` |
| S5 | `@id` / `sameAs` on Org/WebSite | observable / derived | Field presence |
| A1 | Definition pattern density | derived | Regex in early paragraphs |
| A2 | HowTo / steps | derived | `<ol>` ≥3 or HowTo JSON-LD |
| A3 | Question headings | derived | `?` / who|what|… headings |
| A4 | FAQ density | derived | FAQ-shaped page share |
| H | AEO Health | derived | Weighted mean of T,C,E,S,A (`health-v1`) |

## Non-health product signals (related)

| Signal | Class | Notes |
| --- | --- | --- |
| `llm_mention_rate` / `llm_url_mention_rate` / `query_coverage` | experimental | llm-mention-v1 sample estimates; **not** AI search visibility |
| AI crawler robots allow/disallow | observable | Accessibility only — **never** claim allow ⇒ visibility |
| Google-Extended robots token | observable | Training/grounding control; does not affect Google Search inclusion |
| Site understanding (brand/topics/…) | derived | Deterministic HTML/JSON-LD inference; optional LLM off by default |
| Discovered queries | derived | Generated from site understanding; inspectable |
| Retrieval citation/appearance rates | experimental | Only when `retrieval_enabled=true` / `ai_search_visibility` |
| Competitor co-appearance counts | experimental | Retrieval-only; descriptive, no winner ranking |
| Recommendation priority_score | derived + industry_recommendation | impact×effort with catalog rationale |
| “Answer engines prefer X” causal claims | hypothesis | Not asserted by health-v1; avoid in product copy |

## Change control

1. Do **not** silently change weights, check IDs, or pass-value semantics under `health-v1`.
2. New checks or reweights → publish `health-v2` (+ migration notes).
3. Experimental visibility protocols version separately (`llm-mention-v1`, `ai-search-vis-v1`).
