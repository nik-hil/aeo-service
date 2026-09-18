# AEO MVP — Metric Definitions & Formulas

**formula_version:** `health-v1`  
**Status:** Authoritative for MVP scoring  
**Date:** 2026-09-18 (IST)  
**Provenance default for all health metrics:** `derived_metric`

This document defines original formulas for the AEO MVP. Do not copy competitor branded scores. All component scores are real numbers in **[0, 100]**, clamped after computation. AEO Health is a weighted mean of five components.

---

## 1. Notation

| Symbol | Meaning |
| --- | --- |
| \(T\) | Technical Accessibility Score |
| \(C\) | Content Readiness Score |
| \(E\) | Entity Clarity Score |
| \(S\) | Structured Data Score |
| \(A\) | Answerability Score |
| \(H\) | AEO Health Score |
| \(\mathrm{clamp}(x)\) | \(\max(0, \min(100, x))\) |
| \(w_i\) | Binary or fractional check result in [0, 1] |

**Weights (`health-v1`):**

| Component | Weight |
| --- | --- |
| Technical Accessibility \(T\) | 0.25 |
| Content Readiness \(C\) | 0.25 |
| Entity Clarity \(E\) | 0.20 |
| Structured Data \(S\) | 0.15 |
| Answerability \(A\) | 0.15 |

Sum of weights = 1.00.

---

## 2. AEO Health Score

\[
H = \mathrm{clamp}\bigl(0.25\,T + 0.25\,C + 0.20\,E + 0.15\,S + 0.15\,A\bigr)
\]

- **Type:** `derived_metric`
- **formula_version:** `health-v1`
- **Display:** one decimal place
- **Storage:** full float in `score_components` where `component='health'`

Health is computed **only** from crawl/analysis evidence. Visibility experiment rates are **not** inputs to \(H\).

---

## 3. Technical Accessibility Score \(T\)

Evaluated primarily on the **homepage** (depth 0) plus site-level robots, with penalties if a majority of crawled pages fail key checks.

### Checks (each contributes a weight)

| ID | Check | Pass value \(p_i\) | Weight \(v_i\) |
| --- | --- | --- | --- |
| T1 | Homepage HTTP status in {200, 203} | 1 else 0 | 0.20 |
| T2 | robots.txt fetched and does **not** Disallow the configured UA path `/` for `AEOBot` (if robots missing → 0.5 partial) | 1 / 0.5 / 0 | 0.15 |
| T3 | No `noindex` in robots meta on homepage | 1 else 0 | 0.15 |
| T4 | Canonical URL present and same-host | 1 else 0 | 0.10 |
| T5 | `<title>` non-empty (after strip), length 15–70 chars → 1; present but out of range → 0.5; missing → 0 | 1 / 0.5 / 0 | 0.10 |
| T6 | Meta description present, length 50–160 → 1; present else → 0.5; missing → 0 | 1 / 0.5 / 0 | 0.10 |
| T7 | JS-risk heuristic low: ratio of inline script bytes / HTML bytes ≤ 0.35 **and** body text length ≥ 200 chars → 1; else if body text ≥ 200 → 0.5; else 0 | 1 / 0.5 / 0 | 0.10 |
| T8 | Share of crawled pages with status 2xx ≥ 0.8 → 1; ≥ 0.5 → 0.5; else 0 | 1 / 0.5 / 0 | 0.10 |

\[
T = \mathrm{clamp}\Bigl(100 \times \sum_i v_i p_i\Bigr)
\]

Note: \(\sum v_i = 1.00\).

**Evidence codes (examples):** `TECH_HOME_STATUS`, `TECH_ROBOTS`, `TECH_NOINDEX`, `TECH_CANONICAL`, `TECH_TITLE`, `TECH_META_DESC`, `TECH_JS_RISK`, `TECH_PAGE_SUCCESS_RATE`.

---

## 4. Content Readiness Score \(C\)

Averaged across crawled HTML pages with status 2xx; pages with fetch errors excluded from the mean. If zero eligible pages, \(C = 0\).

### Per-page score \(C_p\)

| ID | Check | \(p_i\) | \(v_i\) |
| --- | --- | --- | --- |
| C1 | Heading hierarchy: exactly one `h1`; no heading level skips (e.g. h1→h3) | 1 if both; 0.5 if one `h1` but skips; 0 else | 0.25 |
| C2 | Answer-first: first substantial block (`p` or list) within 500 chars of main content start contains a declarative sentence ≥ 40 chars | 1 / 0 | 0.25 |
| C3 | FAQ/Q&A shape: ≥1 pair of question-like heading/bold + following paragraph, **or** JSON-LD FAQPage elsewhere on page credited at page level | 1 / 0 | 0.20 |
| C4 | Usable paragraphs: count of `<p>` with 40–300 words between 2 and 30 → 1; 1 or >30 → 0.5; 0 → 0 | 1 / 0.5 / 0 | 0.15 |
| C5 | Word count in visible text estimate 300–5000 → 1; 100–299 or 5001–8000 → 0.5; else 0 | 1 / 0.5 / 0 | 0.15 |

\[
C_p = 100 \times \sum_i v_i p_i, \quad C = \mathrm{clamp}\bigl(\mathrm{mean}_p C_p\bigr)
\]

**Evidence codes:** `CONTENT_HEADINGS`, `CONTENT_ANSWER_FIRST`, `CONTENT_FAQ_SHAPE`, `CONTENT_PARAGRAPHS`, `CONTENT_WORDCOUNT`.

---

## 5. Entity Clarity Score \(E\)

Site-level, using homepage + about-like pages (URL path contains `about`, `company`, `team` if present).

| ID | Check | \(p_i\) | \(v_i\) |
| --- | --- | --- | --- |
| E1 | Brand token consistency: most frequent proper-cased brand candidate (from `<title>`, `og:site_name`, hostname label) appears in ≥70% of page titles | 1 / 0.5 / 0 | 0.35 |
| E2 | Organization signal: JSON-LD `@type` Organization/LocalBusiness **or** clear copyright/org name in footer | 1 / 0.5 / 0 | 0.30 |
| E3 | Contact or sameAs: `sameAs` in JSON-LD **or** `mailto:` / contact path link on homepage/about | 1 / 0 | 0.20 |
| E4 | Ambiguity penalty inverse: if ≥3 divergent brand strings (edit distance >2) across titles → 0; 2 divergent → 0.5; else 1 | 1 / 0.5 / 0 | 0.15 |

\[
E = \mathrm{clamp}\Bigl(100 \times \sum_i v_i p_i\Bigr)
\]

**Evidence codes:** `ENTITY_BRAND_CONSISTENCY`, `ENTITY_ORG_SIGNAL`, `ENTITY_CONTACT_SAMEAS`, `ENTITY_AMBIGUITY`.

---

## 6. Structured Data Score \(S\)

| ID | Check | \(p_i\) | \(v_i\) |
| --- | --- | --- | --- |
| S1 | ≥1 parseable JSON-LD block on homepage | 1 / 0 | 0.30 |
| S2 | Share of 2xx pages with ≥1 parseable JSON-LD ≥ 0.4 → 1; ≥ 0.2 → 0.5; else 0 | 1 / 0.5 / 0 | 0.20 |
| S3 | Type fit: at least one of `{Organization, WebSite, WebPage, Article, FAQPage, Product, HowTo, BreadcrumbList}` present site-wide | 1 / 0 | 0.25 |
| S4 | Hygiene: among parsed nodes, fraction with `@type` present ≥ 0.9 → 1; ≥ 0.5 → 0.5; else 0 | 1 / 0.5 / 0 | 0.15 |
| S5 | `@id` or `sameAs` present on ≥1 Organization/WebSite node | 1 / 0 | 0.10 |

Invalid JSON-LD (parse error) counts as non-parseable and emits evidence `SD_PARSE_ERROR`.

\[
S = \mathrm{clamp}\Bigl(100 \times \sum_i v_i p_i\Bigr)
\]

**Evidence codes:** `SD_HOME_JSONLD`, `SD_COVERAGE`, `SD_TYPE_FIT`, `SD_HYGIENE`, `SD_ID_SAMEAS`, `SD_PARSE_ERROR`.

---

## 7. Answerability Score \(A\)

Measures whether a page offers extractable question→passage pairs (AEO-oriented), derived from content heuristics (not from live AI).

| ID | Check | \(p_i\) | \(v_i\) |
| --- | --- | --- | --- |
| A1 | Definition pattern: phrase matching `(?i)\b(is|are|means|refers to)\b` in first 2 paragraphs on ≥30% of pages → 1; ≥10% → 0.5; else 0 | 1 / 0.5 / 0 | 0.25 |
| A2 | HowTo / steps: ordered list with ≥3 steps **or** HowTo JSON-LD on ≥1 page | 1 / 0 | 0.25 |
| A3 | Question headings: count of headings ending in `?` or matching `^(who|what|when|where|why|how)\b` ≥ 2 site-wide → 1; 1 → 0.5; 0 → 0 | 1 / 0.5 / 0 | 0.25 |
| A4 | FAQ density: FAQ-shaped pages / 2xx pages ≥ 0.15 → 1; ≥ 0.05 → 0.5; else 0 | 1 / 0.5 / 0 | 0.25 |

\[
A = \mathrm{clamp}\Bigl(100 \times \sum_i v_i p_i\Bigr)
\]

**Evidence codes:** `ANS_DEFINITION`, `ANS_HOWTO`, `ANS_QUESTION_HEADINGS`, `ANS_FAQ_DENSITY`.

---

## 8. AI visibility metrics (estimates)

**protocol:** `vis-exp-v1` (see AI_VISIBILITY.md). These are **not** part of \(H\).

Let \(R\) = total observation runs = \(P \times N\) where \(P\) = number of prompts, \(N\) = runs per prompt.  
Let \(M\) = runs with `detected_mention=1`.  
Let \(K\) = runs with `detected_citation=1`.  
Let \(Q_m\) = number of distinct prompts with ≥1 mention across their runs.

### AI Mention Rate

\[
\mathrm{AIMentionRate} = \frac{M}{R} \quad (R > 0);\ \mathrm{else\ null}
\]

- provenance: `estimate` (or `synthetic_demo` in demo)
- store numerator \(M\), denominator \(R\)

### AI Citation Rate

\[
\mathrm{AICitationRate} = \frac{K}{R} \quad (R > 0);\ \mathrm{else\ null}
\]

### Query Coverage

\[
\mathrm{QueryCoverage} = \frac{Q_m}{P} \quad (P > 0);\ \mathrm{else\ null}
\]

---

## 9. Recommendation Priority

See `RECOMMENDATIONS.md`. Summary:

\[
\mathrm{priority\_score} = \mathrm{impact} \times \mathrm{effort\_weight}
\]

| effort | effort_weight |
| --- | --- |
| S | 1.0 |
| M | 0.7 |
| L | 0.4 |

`impact` ∈ [0, 1] assigned from catalog + severity boosts.

---

## 10. Worked example (`health-v1`)

Suppose analyzers produce:

| Component | Score |
| --- | --- |
| \(T\) | 80.0 |
| \(C\) | 70.0 |
| \(E\) | 65.0 |
| \(S\) | 55.0 |
| \(A\) | 75.0 |

\[
\begin{align*}
H &= 0.25(80) + 0.25(70) + 0.20(65) + 0.15(55) + 0.15(75) \\
&= 20 + 17.5 + 13 + 8.25 + 11.25 \\
&= 70.0
\end{align*}
\]

Display: **70.0**

### Technical sub-example

Homepage 200 (1), robots allow (1), no noindex (1), canonical ok (1), title ok (1), meta desc partial (0.5), JS-risk low (1), 2xx share 0.9 (1):

\[
T = 100\times(0.20+0.15+0.15+0.10+0.10+0.10\times0.5+0.10+0.10) = 100\times0.95 = 95.0
\]

### Visibility sub-example

\(P=5\), \(N=3\), \(R=15\), \(M=6\), \(K=3\), \(Q_m=3\):

- AI Mention Rate = 6/15 = **0.40**
- AI Citation Rate = 3/15 = **0.20**
- Query Coverage = 3/5 = **0.60**

---

## 11. Implementation notes

1. Persist each component + health with `formula_version='health-v1'` and `breakdown_json` listing every \(p_i, v_i\).
2. Changing any weight or check requires a **new** formula_version string (e.g. `health-v2`); never silently mutate `health-v1`.
3. Unit tests must lock the worked example above.
4. Missing optional signals use the partial values defined — do not invent LLM guesses inside `health-v1` (LLM may only annotate findings separately as `llm_assessment`).

---

*End of METRICS.md*
