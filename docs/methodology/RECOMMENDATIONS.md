# AEO MVP — Recommendation Methodology

**Date:** 2026-09-18 (IST)  
**Status:** Authoritative for MVP recommendation engine  
**Consumes:** analysis_evidence, visibility_observations, score_components  
**Produces:** findings + recommendations rows + report sections

---

## 1. Goals

1. Turn evidence into **actionable, site-owned** fixes.
2. Rank by **likely impact for effort** so a small team knows what to do next.
3. Keep every recommendation **auditable** via evidence / observation IDs.
4. Never recommend competitor scraping, buying links, or “guaranteed ChatGPT inclusion.”

---

## 2. Pipeline step

`synthesize_findings` → groups evidence into findings  
`prioritize_recommendations` → maps findings (+ catalog rules) to ranked recommendations

---

## 3. Priority scoring

\[
\mathrm{priority\_score} = \mathrm{impact} \times \mathrm{effort\_weight}
\]

| effort | meaning | effort_weight |
| --- | --- | --- |
| **S** | ≤ half day for one engineer/content owner | 1.0 |
| **M** | ≤ 2 days | 0.7 |
| **L** | multi-day / cross-team | 0.4 |

**impact** ∈ [0.0, 1.0] — base from catalog, then adjusted:

\[
\mathrm{impact} = \mathrm{clamp}_{[0,1]}\bigl(\mathrm{impact_{base}} + \mathrm{severity\_boost} + \mathrm{score\_gap\_boost} + \mathrm{visibility\_boost}\bigr)
\]

| Factor | Rule |
| --- | --- |
| `severity_boost` | high +0.15, medium +0.08, low +0.03, info +0.0 (from strongest linked evidence) |
| `score_gap_boost` | If linked component score < 50 → +0.10; < 70 → +0.05; else 0 |
| `visibility_boost` | If AI Mention Rate < 0.2 and rec is visibility-relevant → +0.05; else 0 |

**Ranking:** descending `priority_score`; ties → higher severity; then ascending `code` (stable).

Assign `rank` = 1..K after sort.

---

## 4. Evidence linking (mandatory)

Every recommendation row **must** include:

- `evidence_ids_json`: ≥1 id from `analysis_evidence` **or** (for pure visibility recs) ≥1 `observation` id reflected via findings
- `finding_ids_json`: ≥1 finding id

API/report shape per recommendation:

```json
{
  "id": "...",
  "code": "REC_ADD_JSONLD_ORG",
  "title": "Add Organization JSON-LD on the homepage",
  "rationale": "No parseable Organization node was found; entity clarity and structured data scores are limited by missing machine-readable identity.",
  "effort": "S",
  "impact": 0.78,
  "priority_score": 0.78,
  "rank": 1,
  "evidence_ids": ["ev_..."],
  "finding_ids": ["find_..."],
  "related_components": ["entity", "structured_data"]
}
```

If a catalog rule matches but evidence IDs are missing, **do not emit** the recommendation (fix bug).

---

## 5. Finding synthesis rules

Findings are intermediate, human-readable groupings:

| category | source |
| --- | --- |
| `readiness` | analyzers / scores |
| `visibility` | experiment metrics / observations |
| `meta` | crawl failures, demo fallback, formula versions |

Severity of a finding = max severity of member evidence (info < low < medium < high).

---

## 6. Recommendation catalog (`rec-catalog-v1`)

Engineers implement as data in `aeo_mvp.recommendations.catalog`.

| code | trigger (any) | effort | impact_base | components |
| --- | --- | --- | --- | --- |
| `REC_FIX_HOME_HTTP` | T1 fail (homepage not 2xx) | S | 0.95 | technical |
| `REC_FIX_ROBOTS_BLOCK` | T2 fail (robots disallow) | S | 0.95 | technical |
| `REC_REMOVE_NOINDEX` | T3 fail | S | 0.90 | technical |
| `REC_ADD_CANONICAL` | T4 fail | S | 0.55 | technical |
| `REC_IMPROVE_TITLE` | T5 ≤ 0.5 | S | 0.50 | technical |
| `REC_ADD_META_DESCRIPTION` | T6 = 0 | S | 0.40 | technical |
| `REC_REDUCE_JS_DEPENDENCY` | T7 = 0 (thin body / high script ratio) | L | 0.85 | technical, content |
| `REC_FIX_HEADING_HIERARCHY` | C1 mean issue on ≥30% pages | M | 0.60 | content |
| `REC_ADD_ANSWER_FIRST` | C2 fail on homepage | M | 0.70 | content, answerability |
| `REC_ADD_FAQ_SECTION` | C3 fail site-wide / A4 low | M | 0.65 | content, answerability |
| `REC_EXPAND_THIN_CONTENT` | C5 low on ≥30% pages | M | 0.55 | content |
| `REC_CONSOLIDATE_BRAND_NAME` | E1 or E4 weak | M | 0.70 | entity |
| `REC_ADD_ORG_SIGNAL` | E2 fail | S | 0.75 | entity |
| `REC_ADD_CONTACT_OR_SAMEAS` | E3 fail | S | 0.45 | entity |
| `REC_ADD_JSONLD_ORG` | S1 fail or no Organization | S | 0.80 | structured_data, entity |
| `REC_BROADEN_JSONLD_COVERAGE` | S2 ≤ 0.5 | M | 0.55 | structured_data |
| `REC_ADD_TYPE_FIT_SCHEMA` | S3 fail | M | 0.60 | structured_data |
| `REC_FIX_JSONLD_PARSE` | any `SD_PARSE_ERROR` | S | 0.70 | structured_data |
| `REC_ADD_HOWTO_OR_STEPS` | A2 fail | M | 0.50 | answerability |
| `REC_ADD_QUESTION_HEADINGS` | A3 = 0 | S | 0.45 | answerability |
| `REC_IMPROVE_CITABLE_URLS` | AI Citation Rate < 0.15 and pages 2xx | M | 0.50 | visibility |
| `REC_CLARIFY_BRAND_IN_COPY` | AI Mention Rate < 0.2 and E weak | M | 0.55 | visibility, entity |
| `REC_REVIEW_DEMO_ONLY` | job ran DemoProvider due to missing credentials | S | 0.20 | meta |

**Visibility-relevant codes** for `visibility_boost`:  
`REC_IMPROVE_CITABLE_URLS`, `REC_CLARIFY_BRAND_IN_COPY`, `REC_ADD_FAQ_SECTION`, `REC_ADD_JSONLD_ORG`, `REC_ADD_ANSWER_FIRST`.

---

## 7. Worked example

Evidence: homepage missing JSON-LD Organization (`SD_HOME_JSONLD` high), Entity Org signal fail (`ENTITY_ORG_SIGNAL` high), \(S=40\), \(E=45\).  
Catalog: `REC_ADD_JSONLD_ORG`, effort S, impact_base 0.80.

\[
\begin{align*}
\mathrm{impact} &= 0.80 + 0.15 + 0.10 + 0 = 1.05 \rightarrow 1.0 \\
\mathrm{priority\_score} &= 1.0 \times 1.0 = 1.0
\end{align*}
\]

Second rec: `REC_ADD_ANSWER_FIRST`, impact_base 0.70, medium severity (+0.08), content score 62 (+0.05), mention rate 0.1 (+0.05):

\[
\mathrm{impact}=0.88,\ \mathrm{effort}=M\ (0.7),\ \mathrm{priority\_score}=0.616
\]

Order: `REC_ADD_JSONLD_ORG` rank 1, `REC_ADD_ANSWER_FIRST` rank 2.

---

## 8. What not to recommend

- Guaranteed inclusion in any AI product  
- Purchasing citations or fake PR  
- Implementing contested `llms.txt` as a silver bullet (optional informational finding only: `FIND_LLMS_TXT_OPTIONAL`, no high-impact rec in MVP)  
- Competitor attacks or scraping consumer UIs  
- Frontend/CMS auto-publish (out of scope)

---

## 9. Testing

1. Given a fixed evidence fixture set, recommendation codes and order are stable.  
2. Every emitted rec has non-empty evidence_ids existing in DB.  
3. Priority formula unit test matches worked example (±0.001).  
4. Demo job produces ≥3 recommendations including at least one structured-data or entity rec.

---

*End of RECOMMENDATIONS.md*
