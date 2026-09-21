"""Central glossary for leadership UI ⓘ definitions.

Definitions are aligned with docs/methodology (health-v1, vis-exp-v1,
content-optimization-v1, provenance lock). Do not overclaim consumer ranking
or treat drafts as published pages.
"""

from __future__ import annotations

from typing import TypedDict


class GlossaryEntry(TypedDict):
    term: str
    short: str
    executive: str
    detail: str
    source: str


GLOSSARY: dict[str, GlossaryEntry] = {
    "aeo_health": {
        "term": "AEO Health",
        "short": "Weighted readiness score (0–100) from crawl/analysis only.",
        "executive": "Overall readiness of your pages for answer engines (0–100). Higher is better. Not a search ranking.",
        "detail": (
            "AEO Health (formula_version health-v1) is a clamped weighted mean: "
            "0.25×Technical + 0.25×Content + 0.20×Entity Clarity + "
            "0.15×Structured Data + 0.15×Answerability. "
            "Visibility experiment rates are not inputs. Provenance: derived_metric."
        ),
        "source": "docs/methodology/METRICS.md",
    },
    "entity_score": {
        "term": "Entity Score",
        "short": "Entity Clarity (E): brand/org consistency on the site.",
        "executive": "How clearly the site states who you are (brand/org). Helps answer engines attribute answers correctly.",
        "detail": (
            "Product label for Entity Clarity Score (E) in health-v1 — brand token "
            "consistency, Organization signal, contact/sameAs, and an ambiguity "
            "penalty. Site-level; not an AI-visibility metric."
        ),
        "source": "docs/methodology/METRICS.md §5",
    },
    "ai_llm_visibility": {
        "term": "AI / LLM Visibility",
        "short": "Sample estimate from a controlled experiment — not rankings.",
        "executive": "Sample estimate of whether models mention your brand/URL in a controlled test — not ChatGPT/Gemini rankings.",
        "detail": (
            "Two experiment kinds exist: llm_mention (non-retrieval mention rates) "
            "and ai_search_visibility (retrieval-enabled API observations). "
            "Metrics are sample estimates under vis-exp-v1. "
            "measures_consumer_ui is always false — this does not reproduce "
            "ChatGPT / Gemini / Perplexity consumer UI ranking."
        ),
        "source": "docs/methodology/AI_VISIBILITY.md",
    },
    "content_gap": {
        "term": "Content Gap",
        "short": "Evidence-backed gap vs a frozen QuerySet (content-gap-v1).",
        "executive": "Places where content is missing or thin for questions buyers ask — evidence-backed, not a health score.",
        "detail": (
            "Deterministic gap types (missing/thin/structure/entity/schema/etc.) "
            "joined to a frozen QuerySet. Page coverage flags are explicit: "
            "coverage_is_not_ai_visibility and coverage_is_not_health_v1 — "
            "gaps are not health scores and not visibility rates."
        ),
        "source": "docs/methodology/CONTENT_OPTIMIZATION_V1.md",
    },
    "optimization_opportunity": {
        "term": "Optimization Opportunity",
        "short": "Prioritized recommendation or optimization brief — not a score.",
        "executive": "Highest-leverage next fixes ranked from recommendations and gaps. Not a separate score.",
        "detail": (
            "There is no separate methodology score named Optimization Opportunity. "
            "In this UI it means a ranked recommendation (rec-catalog-v1) and/or an "
            "optimization brief (opt-brief-v1 action such as expand_section, add_faq). "
            "Ordered deterministically from existing report fields."
        ),
        "source": "docs/methodology/RECOMMENDATIONS.md; opt-brief-v1",
    },
    "query_coverage": {
        "term": "Query Coverage",
        "short": "Share of experiment prompts with ≥1 positive observation.",
        "executive": "Share of test prompts where your brand/URL appeared at least once in the experiment.",
        "detail": (
            "Visibility Query Coverage: fraction of prompts with at least one "
            "mention (llm_mention) or mention/appearance/citation "
            "(ai_search_visibility). Provenance is typically estimate or "
            "synthetic_demo. Distinct from gap-report page_coverage."
        ),
        "source": "docs/methodology/METRICS.md §8",
    },
    "evidence": {
        "term": "Evidence",
        "short": "Observable or derived artifacts linked to findings and recs.",
        "executive": "Snippets and findings that explain why a recommendation or gap exists.",
        "detail": (
            "Crawl/analyzer artifacts (IDs, snippets, codes) attached to findings "
            "and recommendations. Signal classes include observable, derived, and "
            "experimental. Evidence grounds why a recommendation exists."
        ),
        "source": "docs/methodology/SIGNAL_CLASSIFICATION.md",
    },
    "recommendation": {
        "term": "Recommendation",
        "short": "Actionable, evidence-linked fix with effort and impact.",
        "executive": "A concrete fix with effort and expected impact, tied to evidence on the page.",
        "detail": (
            "From rec-catalog-v1: prioritized action with rationale, effort (S/M/L), "
            "impact, and evidence_ids. priority_score = impact × effort_weight "
            "(S=1.0, M=0.7, L=0.4). Ranked for the report."
        ),
        "source": "docs/methodology/RECOMMENDATIONS.md",
    },
    "provenance": {
        "term": "Provenance",
        "short": "How a metric or content claim was produced.",
        "executive": "Where a number or draft came from (observed, derived, estimate, generated).",
        "detail": (
            "Score metrics use labels such as derived_metric, estimate, "
            "synthetic_demo, api_observation. Content/query layers use "
            "observed | derived | compatibility | generated. Drafts are always "
            "generated — never promoted to crawl-observed. The UI must not invent "
            "observed provenance."
        ),
        "source": "docs/architecture/PHASE4_1_1_PROVENANCE_LOCK.md",
    },
}


GUIDE_MARKDOWN = """
# How to read this report

## Story arc
1. **URL** — seed page (single-page) or crawl seed (same-host multi-page).
2. **Analyze** — the UI only calls the secured AEO API; it never fetches the site itself.
3. **AEO Health** — crawl/analysis readiness (`health-v1`), not visibility rankings.
4. **Gaps & opportunities** — content gaps and prioritized recommendations.
5. **Why** — evidence snippets and provenance labels.
6. **Recommended content** — optimization briefs and drafts when the API provides them.

## CURRENT / OBSERVED vs RECOMMENDED
- **CURRENT (observed page signals)** = extracted title, headings, answer blocks from the API — **not a live browser render**.
- **RECOMMENDED** = optimization brief + suggested structure/draft when the API returns one. Skeleton drafts are labeled honestly — **never** a final optimized page.
- **Content gaps** = existing `content_gaps` rows for the page (content-gap-v1) — not health or visibility scores.

## Visibility honesty
Visibility metrics are **sample estimates** under a controlled protocol. They do **not** reproduce ChatGPT / Gemini / Perplexity consumer rankings.

## Multi-page mode
Multi-page means a **same-host crawl from the seed URL** (depth/page caps). It is not a CMS “series” or Hashnode-specific construct.

## Biggest Opportunities ordering
See `services/opportunities.py`: recommendations by rank / priority_score, then high-severity gaps not already covered, capped — fully deterministic from report fields.
"""


def get_entry(key: str) -> GlossaryEntry:
    if key not in GLOSSARY:
        raise KeyError(f"Unknown glossary key: {key}")
    return GLOSSARY[key]


def info_text(key: str) -> str:
    """Short tip for Gradio `info=` / tooltip surfaces (executive-first)."""
    entry = get_entry(key)
    return f"{entry['term']}: {entry['executive']}"


def executive_tip(key: str) -> str:
    """Plain-English tip for KPI ⓘ affordances."""
    return get_entry(key)["executive"]


def detail_text(key: str) -> str:
    entry = get_entry(key)
    return f"**{entry['term']}** — {entry['detail']} _(Source: {entry['source']})_"


def executive_glossary_markdown() -> str:
    lines = ["### Quick glossary (executive)", ""]
    for key in (
        "aeo_health",
        "entity_score",
        "ai_llm_visibility",
        "content_gap",
        "optimization_opportunity",
        "recommendation",
        "provenance",
    ):
        entry = GLOSSARY[key]
        lines.append(f"- **{entry['term']}** ⓘ — {entry['executive']}")
    return "\n".join(lines)


def all_terms_markdown() -> str:
    lines = ["### Technical details & full glossary", ""]
    for key in (
        "aeo_health",
        "entity_score",
        "ai_llm_visibility",
        "content_gap",
        "optimization_opportunity",
        "query_coverage",
        "evidence",
        "recommendation",
        "provenance",
    ):
        entry = GLOSSARY[key]
        lines.append(f"**{entry['term']}** ⓘ")
        lines.append("")
        lines.append(f"*Executive:* {entry['executive']}")
        lines.append("")
        lines.append(entry["detail"])
        lines.append("")
        lines.append(f"*Source: {entry['source']}*")
        lines.append("")
    return "\n".join(lines)
