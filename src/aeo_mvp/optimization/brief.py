"""Stage 5.2 — deterministic ContentOptimizationBrief (content-brief-v1)."""

from __future__ import annotations

from typing import Any

from aeo_mvp.optimization.models import (
    BRIEF_VERSION,
    ContentGapReport,
    ContentOptimizationBrief,
    OutlineSection,
    PageIntelligence,
)

FORBIDDEN_PRACTICES = [
    "keyword_stuffing",
    "fake_statistics",
    "fabricated_citations",
    "unguarded_ranking_promises",
    "invented_customer_quotes",
]

AEO_WRITING_REQUIREMENTS = [
    "Lead with a direct answer in the first paragraph (answer-first).",
    "Use clear H2/H3 sections aligned to real user questions.",
    "Prefer definitions, steps, and comparisons grounded in on-site facts.",
    "Mark uncertainty; never invent stats, citations, or competitor claims.",
    "Keep FAQ answers concise and consistent with body copy.",
    "Use internal links only to real same-host URLs already known or suggested.",
    "Schema must mirror visible content — no orphan FAQPage entries.",
]


def _profile_value(profile: dict[str, Any] | None, key: str) -> Any:
    if not profile:
        return None
    fld = profile.get(key)
    if isinstance(fld, dict):
        if fld.get("omitted"):
            return None
        return fld.get("value")
    return fld


def _brand(profile: dict[str, Any] | None, page: PageIntelligence) -> str | None:
    for key in ("org_name", "brand"):
        v = _profile_value(profile, key)
        if isinstance(v, str) and v.strip():
            return v.strip()
    for e in page.entities:
        if e and not e.startswith("#"):
            return e
    return None


def build_optimization_brief(
    page: PageIntelligence,
    gap_report: ContentGapReport,
    *,
    site_profile: dict[str, Any] | None = None,
    queryset: Any = None,
    config: dict[str, Any] | None = None,
) -> ContentOptimizationBrief:
    """Deterministic brief from page + SiteProfile + QuerySet + config.

    No keyword stuffing / fake stats / fabricated citations.
    """
    _ = queryset  # available for future intent weighting; coverage already in gaps
    cfg = config or {}
    brand = _brand(site_profile, page)
    primary = page.h1 or page.title or (brand and f"About {brand}") or "Untitled page"

    uncovered = [
        r for r in gap_report.query_coverage if r.coverage in ("none", "mention")
    ]
    uncovered.sort(key=lambda r: (r.query_id, r.query_text.lower()))

    retain: list[str] = []
    improve: list[str] = []
    add: list[str] = []
    if page.h1:
        retain.append(f"H1: {page.h1}")
    if page.title and page.title != page.h1:
        retain.append(f"Title cue: {page.title}")
    for h in page.headings[1:6]:
        retain.append(f"H{h.level}: {h.text}")
    if page.meta_description:
        improve.append("Tighten meta description to answer-first summary (120–160 chars).")
    else:
        add.append("Add meta description summarizing the primary answer.")
    if page.word_count < 200:
        improve.append("Expand thin sections with grounded explanations.")
    for row in uncovered[:8]:
        add.append(f"Answer query: {row.query_text}")

    outline: list[OutlineSection] = []
    # Always keep/improve intro
    outline.append(
        OutlineSection(
            heading=primary,
            level=1,
            intent="informational",
            retain_improve_add="improve" if page.h1 else "add",
            related_query_ids=[r.query_id for r in uncovered[:2]],
            notes="Answer-first introduction grounded in page topic.",
        )
    )
    # Existing H2s → retain/improve
    existing_h2 = [h for h in page.headings if h.level == 2]
    for h in existing_h2[:6]:
        outline.append(
            OutlineSection(
                heading=h.text,
                level=2,
                intent="informational",
                retain_improve_add="retain",
                notes="Preserve existing section; clarify answer density.",
            )
        )
    # Add sections for uncovered queries
    seen_heads = {o.heading.lower() for o in outline}
    for row in uncovered[:6]:
        head = row.query_text.rstrip("?").strip()
        if not head or head.lower() in seen_heads:
            continue
        seen_heads.add(head.lower())
        outline.append(
            OutlineSection(
                heading=head,
                level=2,
                intent=row.intent or "informational",
                retain_improve_add="add",
                related_query_ids=[row.query_id],
                notes=f"Coverage was {row.coverage}; write a direct answer.",
            )
        )

    questions = []
    for row in uncovered:
        q = row.query_text.strip()
        if not q.endswith("?"):
            q = q + "?"
        if q not in questions:
            questions.append(q)
    for qh in page.faq_coverage.get("question_headings") or []:
        if qh not in questions:
            questions.append(qh)
    questions = questions[:12]

    entities: list[str] = []
    for e in page.entities:
        if e not in entities:
            entities.append(e)
    products = _profile_value(site_profile, "products") or []
    if isinstance(products, list):
        for p in products:
            if p and p not in entities:
                entities.append(str(p))
    entities = entities[:12]

    faq_suggestions = [
        {"question": q, "answer_guidance": "Answer in 2–4 sentences using only known page/site facts."}
        for q in questions[:5]
    ]

    schema_suggestions: list[str] = []
    types = set((page.structured_data or {}).get("types") or [])
    genre = _profile_value(site_profile, "site_genre") or cfg.get("site_genre")
    if "Article" not in types and "BlogPosting" not in types:
        schema_suggestions.append("Article")
    if faq_suggestions and "FAQPage" not in types:
        schema_suggestions.append("FAQPage")
    if genre == "ecommerce" and "Product" not in types:
        schema_suggestions.append("Product")
    if genre == "documentation" and "HowTo" not in types:
        schema_suggestions.append("HowTo")
    schema_suggestions = sorted(set(schema_suggestions))

    link_suggestions: list[dict[str, str]] = []
    for link in page.internal_links[:5]:
        link_suggestions.append(
            {"url": link["url"], "anchor": link.get("anchor") or link["url"], "action": "retain"}
        )
    important = []
    if site_profile:
        important = site_profile.get("important_pages") or []
        if isinstance(important, dict):
            important = important.get("value") or []
    for item in important[:5]:
        if isinstance(item, dict) and item.get("url"):
            if not any(x["url"] == item["url"] for x in link_suggestions):
                link_suggestions.append(
                    {
                        "url": item["url"],
                        "anchor": item.get("role") or item["url"],
                        "action": "consider",
                    }
                )

    meta = page.meta_description
    if not meta:
        meta = f"{primary}."
        if brand:
            meta = f"{primary} — {brand}."
        meta = meta[:155]

    title = page.title or primary
    if brand and brand.lower() not in (title or "").lower() and len(title) < 45:
        title = f"{title} | {brand}"

    return ContentOptimizationBrief(
        schema_version=BRIEF_VERSION,
        page_url=page.url,
        proposed_title=title[:70],
        proposed_meta_description=meta[:160],
        proposed_h1=primary[:120],
        outline=outline,
        retain=retain,
        improve=improve,
        add=add,
        questions_to_answer=questions,
        entities_to_cover=entities,
        faq_suggestions=faq_suggestions,
        schema_suggestions=schema_suggestions,
        internal_link_suggestions=link_suggestions,
        aeo_writing_requirements=list(AEO_WRITING_REQUIREMENTS),
        forbidden_practices=list(FORBIDDEN_PRACTICES),
        related_gap_ids=[g.id for g in gap_report.gaps],
        warnings=[],
    )
