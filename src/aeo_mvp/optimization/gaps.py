"""Stage 5.1 — deterministic ContentGapReport (content-gap-v1)."""

from __future__ import annotations

import hashlib
from typing import Any

from aeo_mvp.queries.evidence import normalize_provenance
from aeo_mvp.optimization.coverage import assess_query_coverage, summarize_coverage
from aeo_mvp.optimization.models import (
    GAP_VERSION,
    ContentGap,
    ContentGapReport,
    GapCategory,
    GapSeverity,
    PageIntelligence,
)


def _gap_id(category: str, *parts: str) -> str:
    h = hashlib.sha256("|".join([category, *parts]).encode()).hexdigest()[:10]
    return f"gap_{category}_{h}"


def _sev_rank(s: GapSeverity) -> int:
    return {"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4}[s]


def _cat_rank(c: GapCategory) -> int:
    order = [
        "query",
        "topic",
        "entity",
        "qa",
        "intent",
        "section",
        "evidence",
        "answerability",
        "internal_link",
        "metadata",
        "structured_data",
    ]
    return order.index(c) if c in order else 99


def build_content_gap_report(
    page: PageIntelligence,
    queryset: Any,
    *,
    site_profile: dict[str, Any] | None = None,
) -> ContentGapReport:
    """Build content-gap-v1 from page intelligence + queryset.

    Coverage is page-content overlap, not AI visibility.
    """
    gaps: list[ContentGap] = []
    coverage_rows = assess_query_coverage(page, queryset)
    summary = summarize_coverage(coverage_rows)
    profile = site_profile or {}

    # --- query gaps ---
    for row in coverage_rows:
        if row.coverage in ("none", "mention"):
            sev: GapSeverity = "high" if row.coverage == "none" else "medium"
            gaps.append(
                ContentGap(
                    id=_gap_id("query", row.query_id, row.coverage),
                    category="query",
                    severity=sev,
                    query_ids=[row.query_id],
                    explanation=(
                        f"Query '{row.query_text}' has coverage={row.coverage} on page"
                    ),
                    evidence=[
                        {
                            "evidence_class": "article_body",
                            "provenance": normalize_provenance("derived"),
                            "snippet": row.note,
                            "matched_signals": row.matched_signals,
                        }
                    ],
                    action=(
                        "Add a dedicated section that directly answers this query "
                        "using on-page facts only."
                    ),
                    confidence=0.72 if row.coverage == "none" else 0.55,
                    provenance="derived",
                    coverage=row.coverage,
                )
            )

    # --- topic gaps from profile / queryset ---
    profile_topics: list[str] = []
    for key in ("primary_topics", "secondary_topics"):
        fld = profile.get(key) or {}
        val = fld.get("value") if isinstance(fld, dict) else None
        if isinstance(val, list):
            profile_topics.extend(str(x) for x in val)
    page_topics_l = {t.lower() for t in page.topics}
    for topic in sorted({t.strip() for t in profile_topics if t and t.strip()}, key=str.lower):
        if topic.lower() not in page_topics_l and not any(
            topic.lower() in (page.title or "").lower()
            or topic.lower() in (page.h1 or "").lower()
            for _ in (0,)
        ):
            # also check heading blob
            blob = " ".join(h.text for h in page.headings).lower()
            if topic.lower() not in blob:
                gaps.append(
                    ContentGap(
                        id=_gap_id("topic", topic.lower()),
                        category="topic",
                        severity="medium",
                        query_ids=[],
                        explanation=f"Site topic '{topic}' not reflected on this page",
                        evidence=[
                            {
                                "evidence_class": "tags_series",
                                "provenance": normalize_provenance(
                                    (profile.get("primary_topics") or {}).get("provenance")
                                ),
                                "snippet": topic,
                            }
                        ],
                        action=f"Add a clear section covering '{topic}' if relevant to this URL.",
                        confidence=0.48,
                        provenance="derived",
                    )
                )

    # --- entity gaps ---
    profile_entities: list[str] = []
    for key in ("org_name", "products", "authors"):
        fld = profile.get(key) or {}
        val = fld.get("value") if isinstance(fld, dict) else None
        if isinstance(val, list):
            profile_entities.extend(str(x) for x in val)
        elif isinstance(val, str) and val.strip():
            profile_entities.append(val.strip())
    page_ent_l = {e.lower() for e in page.entities}
    blob = _page_lower(page)
    for ent in sorted({e for e in profile_entities if e}, key=str.lower):
        if ent.lower() not in page_ent_l and ent.lower() not in blob:
            gaps.append(
                ContentGap(
                    id=_gap_id("entity", ent.lower()),
                    category="entity",
                    severity="low",
                    explanation=f"Entity '{ent}' from site profile missing on page",
                    evidence=[
                        {
                            "evidence_class": "metadata",
                            "provenance": normalize_provenance("derived"),
                            "snippet": ent,
                        }
                    ],
                    action=f"Mention '{ent}' with a grounded definition or role statement.",
                    confidence=0.4,
                    provenance="derived",
                )
            )

    # --- QA / FAQ ---
    faq = page.faq_coverage or {}
    if not faq.get("has_faq_schema") and int(faq.get("question_count") or 0) == 0:
        gaps.append(
            ContentGap(
                id=_gap_id("qa", page.url or "page"),
                category="qa",
                severity="medium",
                explanation="No FAQ schema and no question-shaped headings observed",
                evidence=[
                    {
                        "evidence_class": "jsonld",
                        "provenance": normalize_provenance(faq.get("provenance")),
                        "snippet": "faq_missing",
                    }
                ],
                action="Add 2–5 question headings with concise answers; consider FAQPage JSON-LD.",
                confidence=0.66,
                provenance="derived",
            )
        )

    # --- intent gaps (from uncovered queries) ---
    intents_missing: dict[str, list[str]] = {}
    for row in coverage_rows:
        if row.coverage in ("none", "mention") and row.intent:
            intents_missing.setdefault(row.intent, []).append(row.query_id)
    for intent, qids in sorted(intents_missing.items()):
        gaps.append(
            ContentGap(
                id=_gap_id("intent", intent),
                category="intent",
                severity="medium",
                query_ids=sorted(qids),
                explanation=f"Intent '{intent}' under-covered relative to queryset",
                evidence=[
                    {
                        "evidence_class": "article_body",
                        "provenance": "derived",
                        "snippet": f"uncovered_queries={len(qids)}",
                    }
                ],
                action=f"Add content blocks that serve '{intent}' queries without stuffing.",
                confidence=0.58,
                provenance="derived",
            )
        )

    # --- section / thin content ---
    if page.word_count < 120 or page.body_signals.get("empty"):
        gaps.append(
            ContentGap(
                id=_gap_id("section", "thin"),
                category="section",
                severity="critical" if page.word_count < 40 else "high",
                explanation=f"Thin or empty body (word_count={page.word_count})",
                evidence=[
                    {
                        "evidence_class": "article_body",
                        "provenance": "derived",
                        "snippet": f"word_count={page.word_count}",
                    }
                ],
                action="Expand with answer-first sections grounded in known site facts.",
                confidence=0.8,
                provenance="derived",
            )
        )
    elif len(page.headings) < 2:
        gaps.append(
            ContentGap(
                id=_gap_id("section", "headings"),
                category="section",
                severity="medium",
                explanation="Fewer than two headings; weak section structure",
                evidence=[
                    {
                        "evidence_class": "title_h1",
                        "provenance": "observed",
                        "snippet": f"heading_count={len(page.headings)}",
                    }
                ],
                action="Introduce H2 sections aligned to uncovered queries/topics.",
                confidence=0.62,
                provenance="derived",
            )
        )

    # --- evidence / answerability ---
    ans = page.answerability_signals or {}
    if not ans.get("answer_first_heuristic"):
        gaps.append(
            ContentGap(
                id=_gap_id("answerability", "answer_first"),
                category="answerability",
                severity="medium",
                explanation="Page does not lead with a clear declarative answer",
                evidence=[
                    {
                        "evidence_class": "article_body",
                        "provenance": normalize_provenance(ans.get("provenance")),
                        "snippet": "answer_first_heuristic=false",
                    }
                ],
                action="Open with a 40+ character direct answer sentence.",
                confidence=0.5,
                provenance="derived",
            )
        )
    if not ans.get("has_definition_pattern") and not ans.get("has_howto_steps"):
        gaps.append(
            ContentGap(
                id=_gap_id("evidence", "definition_howto"),
                category="evidence",
                severity="low",
                explanation="No definition or how-to step patterns observed",
                evidence=[
                    {
                        "evidence_class": "article_body",
                        "provenance": "derived",
                        "snippet": "missing_definition_and_howto",
                    }
                ],
                action="Add a short definition and/or numbered steps where truthful.",
                confidence=0.45,
                provenance="derived",
            )
        )

    # --- internal links ---
    if len(page.internal_links) < 1 and not page.body_signals.get("empty"):
        gaps.append(
            ContentGap(
                id=_gap_id("internal_link", page.url or "page"),
                category="internal_link",
                severity="low",
                explanation="No same-host internal links observed",
                evidence=[
                    {
                        "evidence_class": "url_path",
                        "provenance": "observed",
                        "snippet": "internal_links=0",
                    }
                ],
                action="Add contextual links to related owned pages.",
                confidence=0.55,
                provenance="derived",
            )
        )

    # --- metadata ---
    if not page.title:
        gaps.append(
            ContentGap(
                id=_gap_id("metadata", "title"),
                category="metadata",
                severity="high",
                explanation="Missing document title",
                evidence=[
                    {
                        "evidence_class": "title_h1",
                        "provenance": normalize_provenance(None),
                        "snippet": "title_missing",
                    }
                ],
                action="Set a unique, descriptive <title> matching the H1 intent.",
                confidence=0.9,
                provenance="derived",
            )
        )
    if not page.meta_description:
        gaps.append(
            ContentGap(
                id=_gap_id("metadata", "meta"),
                category="metadata",
                severity="medium",
                explanation="Missing meta description",
                evidence=[
                    {
                        "evidence_class": "og_meta",
                        "provenance": normalize_provenance(None),
                        "snippet": "meta_description_missing",
                    }
                ],
                action="Add a 120–160 character meta description summarizing the answer.",
                confidence=0.85,
                provenance="derived",
            )
        )
    if not page.h1:
        gaps.append(
            ContentGap(
                id=_gap_id("metadata", "h1"),
                category="metadata",
                severity="high",
                explanation="Missing H1",
                evidence=[
                    {
                        "evidence_class": "title_h1",
                        "provenance": normalize_provenance(None),
                        "snippet": "h1_missing",
                    }
                ],
                action="Add a single H1 that states the page's primary answer topic.",
                confidence=0.88,
                provenance="derived",
            )
        )

    # --- structured data ---
    sd = page.structured_data or {}
    types = set(sd.get("types") or [])
    if not types:
        gaps.append(
            ContentGap(
                id=_gap_id("structured_data", "missing"),
                category="structured_data",
                severity="medium",
                explanation="No JSON-LD types observed",
                evidence=[
                    {
                        "evidence_class": "jsonld",
                        "provenance": normalize_provenance(sd.get("provenance")),
                        "snippet": "jsonld_absent",
                    }
                ],
                action="Add appropriate schema.org types (Article/FAQPage/HowTo/Product).",
                confidence=0.7,
                provenance="derived",
            )
        )
    elif "FAQPage" not in types and int(faq.get("question_count") or 0) >= 2:
        gaps.append(
            ContentGap(
                id=_gap_id("structured_data", "faqpage"),
                category="structured_data",
                severity="low",
                explanation="Question headings present but FAQPage schema missing",
                evidence=[
                    {
                        "evidence_class": "jsonld",
                        "provenance": "derived",
                        "snippet": f"types={sorted(types)}",
                    }
                ],
                action="Emit FAQPage JSON-LD mirroring on-page Q&A pairs only.",
                confidence=0.6,
                provenance="derived",
            )
        )

    # Stable sort: severity → category → id
    gaps.sort(key=lambda g: (_sev_rank(g.severity), _cat_rank(g.category), g.id))

    return ContentGapReport(
        schema_version=GAP_VERSION,
        page_url=page.url,
        gaps=gaps,
        query_coverage=coverage_rows,
        coverage_summary=summary,
        warnings=[],
    )


def _page_lower(page: PageIntelligence) -> str:
    return " ".join(
        [
            page.title or "",
            page.meta_description or "",
            page.h1 or "",
            " ".join(h.text for h in page.headings),
            " ".join(page.topics),
            " ".join(page.entities),
        ]
    ).lower()
