"""rec-catalog-v1 recommendation definitions."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RecDef:
    code: str
    title: str
    rationale_template: str
    effort: str  # S|M|L
    impact_base: float
    components: tuple[str, ...]
    visibility_relevant: bool = False


EFFORT_WEIGHT = {"S": 1.0, "M": 0.7, "L": 0.4}

VISIBILITY_RELEVANT_CODES = frozenset(
    {
        "REC_IMPROVE_CITABLE_URLS",
        "REC_CLARIFY_BRAND_IN_COPY",
        "REC_ADD_FAQ_SECTION",
        "REC_ADD_JSONLD_ORG",
        "REC_ADD_ANSWER_FIRST",
    }
)

REC_CATALOG: dict[str, RecDef] = {
    "REC_FIX_HOME_HTTP": RecDef(
        "REC_FIX_HOME_HTTP",
        "Fix homepage HTTP status",
        "Homepage did not return 200/203; answer engines cannot reliably fetch the primary URL.",
        "S",
        0.95,
        ("technical",),
    ),
    "REC_FIX_ROBOTS_BLOCK": RecDef(
        "REC_FIX_ROBOTS_BLOCK",
        "Allow AEOBot (and similar) in robots.txt",
        "robots.txt appears to disallow crawling of the site root for the analysis user-agent.",
        "S",
        0.95,
        ("technical",),
    ),
    "REC_REMOVE_NOINDEX": RecDef(
        "REC_REMOVE_NOINDEX",
        "Remove noindex from homepage",
        "Homepage robots meta includes noindex, which blocks indexing and citation surfaces.",
        "S",
        0.90,
        ("technical",),
    ),
    "REC_ADD_CANONICAL": RecDef(
        "REC_ADD_CANONICAL",
        "Add a same-host canonical URL on the homepage",
        "A clear canonical helps consolidating signals for the preferred URL.",
        "S",
        0.55,
        ("technical",),
    ),
    "REC_IMPROVE_TITLE": RecDef(
        "REC_IMPROVE_TITLE",
        "Improve homepage title length and clarity",
        "Title is missing or outside the 15–70 character guidance used in health-v1.",
        "S",
        0.50,
        ("technical",),
    ),
    "REC_ADD_META_DESCRIPTION": RecDef(
        "REC_ADD_META_DESCRIPTION",
        "Add a meta description",
        "Homepage lacks a meta description; short summaries help snippet and overview surfaces.",
        "S",
        0.40,
        ("technical",),
    ),
    "REC_REDUCE_JS_DEPENDENCY": RecDef(
        "REC_REDUCE_JS_DEPENDENCY",
        "Reduce JS-only content risk",
        "Body text is thin or inline script ratio is high; serve meaningful HTML without relying on scripts.",
        "L",
        0.85,
        ("technical", "content"),
    ),
    "REC_FIX_HEADING_HIERARCHY": RecDef(
        "REC_FIX_HEADING_HIERARCHY",
        "Fix heading hierarchy",
        "Multiple pages have missing/duplicate h1 or skipped heading levels, hurting extractability.",
        "M",
        0.60,
        ("content",),
    ),
    "REC_ADD_ANSWER_FIRST": RecDef(
        "REC_ADD_ANSWER_FIRST",
        "Lead the homepage with an answer-first paragraph",
        "Homepage lacks an early declarative answer block of sufficient length.",
        "M",
        0.70,
        ("content", "answerability"),
        visibility_relevant=True,
    ),
    "REC_ADD_FAQ_SECTION": RecDef(
        "REC_ADD_FAQ_SECTION",
        "Add FAQ / Q&A sections",
        "Few pages show FAQ/Q&A shape; question-aligned passages improve answerability.",
        "M",
        0.65,
        ("content", "answerability"),
        visibility_relevant=True,
    ),
    "REC_EXPAND_THIN_CONTENT": RecDef(
        "REC_EXPAND_THIN_CONTENT",
        "Expand thin pages",
        "Multiple pages fall below recommended visible word-count ranges.",
        "M",
        0.55,
        ("content",),
    ),
    "REC_CONSOLIDATE_BRAND_NAME": RecDef(
        "REC_CONSOLIDATE_BRAND_NAME",
        "Consolidate brand naming across titles",
        "Brand token consistency is weak or titles diverge, reducing entity clarity.",
        "M",
        0.70,
        ("entity",),
    ),
    "REC_ADD_ORG_SIGNAL": RecDef(
        "REC_ADD_ORG_SIGNAL",
        "Add a clear Organization signal",
        "No strong Organization JSON-LD or footer identity was detected.",
        "S",
        0.75,
        ("entity",),
    ),
    "REC_ADD_CONTACT_OR_SAMEAS": RecDef(
        "REC_ADD_CONTACT_OR_SAMEAS",
        "Add contact or sameAs links",
        "Contact mailto/path or schema.org sameAs was not found on homepage/about.",
        "S",
        0.45,
        ("entity",),
    ),
    "REC_ADD_JSONLD_ORG": RecDef(
        "REC_ADD_JSONLD_ORG",
        "Add Organization JSON-LD on the homepage",
        "No parseable Organization node was found; entity clarity and structured data scores are limited by missing machine-readable identity.",
        "S",
        0.80,
        ("structured_data", "entity"),
        visibility_relevant=True,
    ),
    "REC_BROADEN_JSONLD_COVERAGE": RecDef(
        "REC_BROADEN_JSONLD_COVERAGE",
        "Broaden JSON-LD coverage across key pages",
        "Fewer than 40% of successful pages expose parseable JSON-LD.",
        "M",
        0.55,
        ("structured_data",),
    ),
    "REC_ADD_TYPE_FIT_SCHEMA": RecDef(
        "REC_ADD_TYPE_FIT_SCHEMA",
        "Add well-known schema types",
        "No Organization/WebSite/Article/FAQPage/HowTo (etc.) types were detected site-wide.",
        "M",
        0.60,
        ("structured_data",),
    ),
    "REC_FIX_JSONLD_PARSE": RecDef(
        "REC_FIX_JSONLD_PARSE",
        "Fix invalid JSON-LD",
        "One or more JSON-LD blocks failed to parse; invalid structured data cannot be used.",
        "S",
        0.70,
        ("structured_data",),
    ),
    "REC_ADD_HOWTO_OR_STEPS": RecDef(
        "REC_ADD_HOWTO_OR_STEPS",
        "Add HowTo or step-by-step lists",
        "No ordered steps (≥3) or HowTo JSON-LD was found.",
        "M",
        0.50,
        ("answerability",),
    ),
    "REC_ADD_QUESTION_HEADINGS": RecDef(
        "REC_ADD_QUESTION_HEADINGS",
        "Add question-style headings",
        "No question headings were detected; Q-shaped headings help map queries to passages.",
        "S",
        0.45,
        ("answerability",),
    ),
    "REC_IMPROVE_CITABLE_URLS": RecDef(
        "REC_IMPROVE_CITABLE_URLS",
        "Publish stable, citable URLs in content",
        "Sample citation rate is low; ensure key pages have clear URLs and are referenced in authoritative copy.",
        "M",
        0.50,
        ("visibility",),
        visibility_relevant=True,
    ),
    "REC_CLARIFY_BRAND_IN_COPY": RecDef(
        "REC_CLARIFY_BRAND_IN_COPY",
        "Clarify brand naming in on-page copy",
        "Sample mention rate is low and entity signals are weak; use the preferred brand string consistently.",
        "M",
        0.55,
        ("visibility", "entity"),
        visibility_relevant=True,
    ),
    "REC_REVIEW_DEMO_ONLY": RecDef(
        "REC_REVIEW_DEMO_ONLY",
        "Re-run with live credentials when ready",
        "This job used DemoProvider because live credentials were unavailable; visibility rates are synthetic.",
        "S",
        0.20,
        ("meta",),
    ),
}
