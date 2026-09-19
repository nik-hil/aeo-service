"""opt-brief-v1 — deterministic ContentOptimizationBrief (zero LLM)."""

from __future__ import annotations

import hashlib
import re
from typing import Any
from urllib.parse import urlparse

from aeo_mvp.content.models import (
    BRIEF_VERSION,
    CONTENT_OPTIMIZATION_METHODOLOGY,
    GAP_VERSION,
    PAGE_INTEL_VERSION,
    RESEARCHER_GAP_TAXONOMY,
    BriefAction,
    ContentChange,
    ContentGap,
    ContentGapReport,
    ContentOptimizationBrief,
    EditOp,
    OutlineSection,
    PageIntelligence,
    QueryCoverageRow,
)

ANTI_PATTERNS = [
    "keyword_stuffing",
    "fake_citations",
    "fabricated_statistics",
    "coverage_labeled_as_ai_visibility",
    "coverage_folded_into_health_v1",
    "folding_page_score_into_sov_or_health",
    "unguarded_ranking_or_citation_promises",
    "guaranteed_inclusion",
    "llms_txt_as_silver_bullet",
    "thin_page_farm_per_query",
    "opaque_content_aeo_score",
]

DO_PRINCIPLES = [
    "answer_first_passages",
    "people_first_structure",
    "real_citations_only_when_observed",
    "genre_gated_formats",
    "evidence_linked_recommendations",
    "one_strong_answer_unit_per_important_probe",
]

AEO_WRITING_REQUIREMENTS = [
    "Lead with a direct answer in the first paragraph (answer-first).",
    "People-first: clear H2/H3 sections aligned to real user questions.",
    "One strong answer unit per important probe — not thin thin pages.",
    "Real citations only when observed on-page or in provided evidence.",
    "Genre-gated formats (SaaS compare/pricing/HowTo; Docs defs/steps; Blog tutorials; Ecommerce specs/PDP).",
    "Evidence-linked recommendations only — never invent proof.",
    "Mark uncertainty; never invent stats, citations, or competitor claims.",
    "Schema must mirror visible content only.",
]

CAVEATS = [
    "Diagnostics ≠ health-v1.",
    "page_coverage ≠ AI-search / LLM-mention visibility.",
    "Page intelligence = extractable answer units; queryset = frozen probes × page_coverage.",
    "Draft text is generated — never feed into QSQ-EVD as observed.",
    "No citation or inclusion guarantees.",
    "Not CMS publish.",
]

_GENRE_FORMAT_GUIDANCE: dict[str, list[str]] = {
    "saas_product": [
        "Prefer compare / pricing / HowTo answer units for SaaS probes.",
        "Keep the same Researcher gap taxonomy; lean format toward commercial clarity.",
    ],
    "documentation": [
        "Prefer definitions and numbered steps for docs probes.",
        "Same taxonomy — emphasize evidence + technical extractability.",
    ],
    "personal_tech_blog": [
        "Prefer tutorial-shaped answer units for blog probes.",
        "Same taxonomy — people-first narrative with clear Q→passage.",
        "Index/listing pages: H1 + brand/schema + internal links — not per-query answer sections.",
    ],
    "ecommerce": [
        "Prefer specs / PDP structured units for ecommerce probes.",
        "Same taxonomy — format + entity/identity + media when helpful.",
    ],
}

_LISTING_HEADING_CUES = (
    "latest articles",
    "command palette",
    "recent posts",
    "all posts",
    "blog",
    "newsletter",
    "tags",
    "series",
)

_STOP = {
    "a",
    "an",
    "the",
    "and",
    "or",
    "to",
    "of",
    "in",
    "on",
    "for",
    "with",
    "how",
    "what",
    "where",
    "when",
    "does",
    "is",
    "are",
    "do",
    "you",
    "your",
    "vs",
    "from",
}


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


def _tokens(text: str) -> set[str]:
    return {
        t
        for t in re.findall(r"[a-z0-9]+", (text or "").lower())
        if len(t) > 2 and t not in _STOP
    }


def _path_is_index(url: str) -> bool:
    if not url:
        return False
    path = urlparse(url).path or "/"
    return path in ("", "/")


def _is_listing_or_index_page(
    page: PageIntelligence,
    site_profile: dict[str, Any] | None,
    *,
    genre: str | None,
) -> bool:
    """Homepage / listing / blog index — not an article or product answer surface.

    Path ``/`` alone is insufficient (many SaaS landings live at ``/`` with an H1).
    """
    page_role = _profile_value(site_profile, "page_role")
    if page_role in ("index", "listing", "homepage", "home"):
        return True

    path_index = _path_is_index(page.url or "")
    heading_blob = " ".join(
        (h.text or "").lower() for h in page.headings[:12]
    ) + " " + " ".join((page.heading_outline or [])[:12]).lower()
    listing_cues = sum(1 for c in _LISTING_HEADING_CUES if c in heading_blob)
    genre_blog = (genre or "") == "personal_tech_blog"

    # Strong listing signals (nav/index chrome)
    if listing_cues >= 2:
        return True
    # Blog index: missing H1 + (site root or listing chrome)
    if genre_blog and not page.h1 and (path_index or listing_cues >= 1):
        return True
    # Generic index without H1 at site root
    if path_index and not page.h1 and page.content_type in ("other", "landing"):
        return True
    # Blog root with listing chrome even if a soft H1 exists later
    if genre_blog and path_index and listing_cues >= 1 and page.content_type == "other":
        return True
    return False


def _gap_ids_for_types(
    gap_by_type: dict[str, list[str]], *types: str, limit: int = 3
) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for t in types:
        for gid in gap_by_type.get(t, []):
            if gid and gid not in seen:
                seen.add(gid)
                out.append(gid)
                if len(out) >= limit:
                    return out
    return out


def _gap_ids_for_queries(
    gap_report: ContentGapReport, query_ids: list[str], *, limit: int = 4
) -> list[str]:
    wanted = {q for q in query_ids if q}
    if not wanted:
        return []
    out: list[str] = []
    for g in gap_report.gaps:
        gids = set(g.query_ids or [])
        if g.query_id:
            gids.add(g.query_id)
        if gids & wanted:
            gid = g.id or g.gap_id
            if gid and gid not in out:
                out.append(gid)
            if len(out) >= limit:
                break
    return out


def _fallback_gap_ids(gap_report: ContentGapReport, *, limit: int = 2) -> list[str]:
    out: list[str] = []
    for g in gap_report.gaps:
        gid = g.id or g.gap_id
        if gid and gid not in out:
            out.append(gid)
        if len(out) >= limit:
            break
    return out


def _evidence_snippet(gap: ContentGap | None) -> str:
    if not gap:
        return ""
    for ev in gap.evidence or []:
        if isinstance(ev, dict):
            snip = ev.get("snippet")
            if snip:
                return str(snip)[:160]
    return (gap.rationale or gap.explanation or "")[:160]


def _gap_by_id(gap_report: ContentGapReport) -> dict[str, ContentGap]:
    out: dict[str, ContentGap] = {}
    for g in gap_report.gaps:
        gid = g.id or g.gap_id
        if gid:
            out[gid] = g
    return out


def _reason_for_gap(
    *,
    base: str,
    query_text: str | None,
    gap: ContentGap | None,
) -> str:
    parts = [base.rstrip(".")]
    if query_text:
        parts.append(f"query=\"{query_text.strip()}\"")
    snip = _evidence_snippet(gap)
    if snip:
        parts.append(f"evidence=\"{snip}\"")
    elif gap and (gap.gap_id or gap.id):
        parts.append(f"gap_id={gap.gap_id or gap.id}")
    return "; ".join(parts)


def _query_fits_article_page(row: QueryCoverageRow, page: PageIntelligence) -> bool:
    """Block cross-article bleed: only thin-probe sections for on-topic probes."""
    page_bits = " ".join(
        [
            page.title or "",
            page.h1 or "",
            " ".join(page.topics or []),
            " ".join(e for e in (page.entities or []) if e),
            " ".join(h.text for h in page.headings[:8]),
        ]
    )
    page_toks = _tokens(page_bits)
    q_toks = _tokens(row.query_text or "")
    if not q_toks:
        return False
    overlap = len(q_toks & page_toks) / max(len(q_toks), 1)
    if overlap >= 0.28:
        return True
    # Thin/partial already on this page with modest overlap is OK
    if row.page_coverage in ("thin", "partial") and overlap >= 0.15:
        return True
    # best_page_url points here
    if row.best_page_url and page.url and row.best_page_url.rstrip("/") == page.url.rstrip(
        "/"
    ):
        return True
    return False


def _index_internal_link_ops(
    page: PageIntelligence,
    gap_report: ContentGapReport,
    gap_by_type: dict[str, list[str]],
) -> list[ContentChange]:
    """Listing pages: point owners to deepen links, not invent article answers."""
    items: list[ContentChange] = []
    link_gap_ids = _gap_ids_for_types(
        gap_by_type, "thin_coverage", "missing_page", "structure_gap", limit=2
    ) or _fallback_gap_ids(gap_report, limit=2)
    gaps_map = _gap_by_id(gap_report)
    primary = gaps_map.get(link_gap_ids[0]) if link_gap_ids else None
    for link in page.internal_links[:4]:
        url = link.get("url") or ""
        anchor = link.get("anchor") or url
        if not url or url.rstrip("/").endswith(urlparse(page.url or "").netloc):
            continue
        items.append(
            ContentChange(
                action="expand",
                target=f"internal_link:{anchor[:60]}",
                reason=_reason_for_gap(
                    base=(
                        "Listing page: strengthen internal link toward the article that "
                        "best answers under-covered probes (do not thin-probe answers on the index)"
                    ),
                    query_text=None,
                    gap=primary,
                ),
                related_gap_ids=list(link_gap_ids),
            )
        )
    if not items and link_gap_ids:
        items.append(
            ContentChange(
                action="add",
                target="internal_links_to_best_articles",
                reason=_reason_for_gap(
                    base=(
                        "Index/listing page should link to best_page articles for thin "
                        "probes rather than hosting per-query answer sections"
                    ),
                    query_text=None,
                    gap=primary,
                ),
                related_gap_ids=list(link_gap_ids),
            )
        )
    return items


def _build_edit_ops(
    page: PageIntelligence,
    brief_outline: list[OutlineSection],
    gap_report: ContentGapReport,
    *,
    listing_index: bool,
    coverage_by_id: dict[str, QueryCoverageRow],
) -> list[ContentChange]:
    items: list[ContentChange] = []
    gap_by_type: dict[str, list[str]] = {}
    gaps_map = _gap_by_id(gap_report)
    for g in gap_report.gaps:
        gid = g.id or g.gap_id
        if gid:
            gap_by_type.setdefault(g.gap_type, []).append(gid)
            if g.kind:
                gap_by_type.setdefault(g.kind, []).append(gid)

    schema_gap_ids = _gap_ids_for_types(
        gap_by_type, "schema_gap", "metadata", limit=2
    ) or _fallback_gap_ids(gap_report, limit=2)
    schema_gap = gaps_map.get(schema_gap_ids[0]) if schema_gap_ids else None

    if page.h1:
        # Retain only if we can cite a real gap context; otherwise skip retain noise.
        if schema_gap_ids:
            items.append(
                ContentChange(
                    action="retain",
                    target="h1",
                    reason=_reason_for_gap(
                        base=f"Existing H1 present ({page.h1!r}); keep single H1",
                        query_text=None,
                        gap=schema_gap,
                    ),
                    related_gap_ids=list(schema_gap_ids)[:1],
                )
            )
    else:
        items.append(
            ContentChange(
                action="add",
                target="h1",
                reason=_reason_for_gap(
                    base="H1 missing — add one preferred brand/topic H1",
                    query_text=None,
                    gap=schema_gap,
                ),
                related_gap_ids=schema_gap_ids,
            )
        )

    if not page.meta_description:
        items.append(
            ContentChange(
                action="add",
                target="meta_description",
                reason=_reason_for_gap(
                    base="Meta description missing — add answer-first brand summary",
                    query_text=None,
                    gap=schema_gap,
                ),
                related_gap_ids=schema_gap_ids,
            )
        )
    else:
        thin_ids = _gap_ids_for_types(
            gap_by_type, "thin_coverage", "entity_mismatch", "structure_gap", limit=2
        ) or schema_gap_ids
        thin_gap = gaps_map.get(thin_ids[0]) if thin_ids else schema_gap
        items.append(
            ContentChange(
                action="expand",
                target="meta_description",
                reason=_reason_for_gap(
                    base=(
                        "Tighten meta description to answer-first summary with preferred "
                        f"brand cues (current={page.meta_description[:80]!r})"
                    ),
                    query_text=None,
                    gap=thin_gap,
                ),
                related_gap_ids=thin_ids,
            )
        )

    # Organization / brand schema on listing or when Blog-only
    types = set((page.structured_data or {}).get("types") or [])
    if listing_index and "Organization" not in types:
        items.append(
            ContentChange(
                action="add",
                target="schema:Organization",
                reason=_reason_for_gap(
                    base=(
                        "Listing/index: add Organization schema with one preferred brand "
                        f"name (observed schema_types={sorted(types)!r})"
                    ),
                    query_text=None,
                    gap=schema_gap,
                ),
                related_gap_ids=schema_gap_ids,
            )
        )

    if page.word_count < 200 and not listing_index:
        thin_qids = [
            r.query_id
            for r in gap_report.coverage_by_query
            if r.page_coverage in ("absent", "thin", "mismatched")
        ][:6]
        body_ids = _gap_ids_for_types(
            gap_by_type, "structure_gap", "thin_coverage", "structure", limit=3
        ) or _gap_ids_for_queries(gap_report, thin_qids, limit=3)
        body_gap = gaps_map.get(body_ids[0]) if body_ids else None
        qtext = None
        if thin_qids and thin_qids[0] in coverage_by_id:
            qtext = coverage_by_id[thin_qids[0]].query_text
        items.append(
            ContentChange(
                action="expand",
                target="body",
                reason=_reason_for_gap(
                    base=f"Thin body (word_count={page.word_count})",
                    query_text=qtext,
                    gap=body_gap,
                ),
                related_gap_ids=body_ids or _fallback_gap_ids(gap_report),
                related_query_ids=thin_qids,
            )
        )

    if listing_index:
        items.extend(_index_internal_link_ops(page, gap_report, gap_by_type))
        # Listing pages: NO per-query section:add thin probes
        action_order = {"retain": 0, "rewrite": 1, "expand": 2, "remove": 3, "add": 4}
        items = [i for i in items if i.related_gap_ids]
        items.sort(key=lambda i: (action_order[i.action], i.target.lower()))
        return items

    for section in brief_outline:
        if section.retain_improve_add == "retain":
            continue
        qids = list(section.related_query_ids)
        # Affinity gate for article section adds
        if section.retain_improve_add == "add" and qids:
            row = coverage_by_id.get(qids[0])
            if row is not None and not _query_fits_article_page(row, page):
                # Route as link / best_page note instead of adding off-topic sections
                linked = _gap_ids_for_queries(gap_report, qids) or _fallback_gap_ids(
                    gap_report, limit=1
                )
                g = gaps_map.get(linked[0]) if linked else None
                best = (g.best_page_url if g else None) or (
                    row.best_page_url if row else None
                )
                items.append(
                    ContentChange(
                        action="add",
                        target="cross_page_link",
                        reason=_reason_for_gap(
                            base=(
                                "Probe is off-topic for this article — link to best_page "
                                f"({best or 'choose matching article'}) instead of adding "
                                "a thin answer section here"
                            ),
                            query_text=row.query_text if row else section.heading,
                            gap=g,
                        ),
                        related_query_ids=qids,
                        related_gap_ids=linked,
                    )
                )
                continue

        linked = _gap_ids_for_queries(gap_report, qids) or _gap_ids_for_types(
            gap_by_type,
            "thin_coverage",
            "missing_page",
            "question_coverage_gap",
            "query",
            limit=3,
        ) or _fallback_gap_ids(gap_report, limit=2)
        g = gaps_map.get(linked[0]) if linked else None
        qtext = None
        if qids and qids[0] in coverage_by_id:
            qtext = coverage_by_id[qids[0]].query_text
        elif section.heading:
            qtext = section.heading
        if section.retain_improve_add == "add":
            items.append(
                ContentChange(
                    action="add",
                    target=f"section:{section.heading}",
                    reason=_reason_for_gap(
                        base=section.notes
                        or "Add on-topic answer section for under-covered probe",
                        query_text=qtext,
                        gap=g,
                    ),
                    related_query_ids=qids,
                    related_gap_ids=linked,
                )
            )
        elif section.retain_improve_add == "improve":
            items.append(
                ContentChange(
                    action="rewrite",
                    target=f"section:{section.heading}",
                    reason=_reason_for_gap(
                        base=section.notes or "Improve answer density for on-topic probe",
                        query_text=qtext,
                        gap=g,
                    ),
                    related_query_ids=qids,
                    related_gap_ids=linked,
                )
            )

    action_order = {"retain": 0, "rewrite": 1, "expand": 2, "remove": 3, "add": 4}
    # Hard requirement: every emitted op cites real gap ids
    items = [i for i in items if i.related_gap_ids]
    items.sort(key=lambda i: (action_order[i.action], i.target.lower()))
    return items


def build_optimization_brief(
    page: PageIntelligence,
    gap_report: ContentGapReport,
    *,
    site_profile: dict[str, Any] | None = None,
    queryset: Any = None,
    config: dict[str, Any] | None = None,
) -> ContentOptimizationBrief:
    """Deterministic opt-brief-v1. Cites inputs. Zero LLM."""
    cfg = config or {}
    brand = _brand(site_profile, page)
    primary = page.h1 or page.title or (brand and f"About {brand}") or "Untitled page"
    genre = _profile_value(site_profile, "site_genre") or cfg.get("site_genre")
    listing_index = _is_listing_or_index_page(page, site_profile, genre=str(genre) if genre else None)

    coverage_by_id = {r.query_id: r for r in gap_report.coverage_by_query if r.query_id}

    uncovered = [
        r
        for r in gap_report.coverage_by_query
        if r.page_coverage in ("absent", "thin", "mismatched")
    ]
    uncovered.sort(key=lambda r: (r.query_id, r.query_text.lower()))

    # Article-only: keep probes that fit this page
    if listing_index:
        section_candidates: list[QueryCoverageRow] = []
        brand_nav = [
            r
            for r in uncovered
            if (r.intent or "") in ("navigational",) or (brand and brand.lower() in (r.query_text or "").lower())
        ]
    else:
        section_candidates = [r for r in uncovered if _query_fits_article_page(r, page)]
        brand_nav = []

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
        improve.append(
            "Tighten meta description to answer-first summary with preferred brand (120–160 chars)."
        )
    else:
        add.append("Add meta description summarizing the primary answer + brand.")
    if listing_index:
        add.append("Add one H1 with preferred brand/topic (listing must not thin-probe article probes).")
        add.append("Add Organization schema with preferred brand name.")
        add.append("Link index cards to best_page articles for thin probes.")
        improve.append("Sequential heading hierarchy: one h1, then h2→h3.")
    elif page.word_count < 200:
        improve.append("Expand thin sections with grounded explanations.")
    for row in section_candidates[:8]:
        add.append(f"Answer query on this page: {row.query_text}")

    outline: list[OutlineSection] = [
        OutlineSection(
            heading=primary if not listing_index or page.h1 else (brand or primary),
            level=1,
            intent="navigational" if listing_index else "informational",
            retain_improve_add="improve" if page.h1 else "add",
            related_query_ids=[
                r.query_id
                for r in (
                    (brand_nav or uncovered)[:2]
                    if listing_index
                    else (section_candidates[:2] if section_candidates else [])
                )
            ],
            notes=(
                "Listing/index: preferred-brand H1 + answer-first intro; not per-query answer sections."
                if listing_index
                else "Answer-first introduction grounded in page topic."
            ),
        )
    ]
    seen_heads = {outline[0].heading.lower()}
    for h in [x for x in page.headings if x.level == 2][:6]:
        outline.append(
            OutlineSection(
                heading=h.text,
                level=2,
                intent="informational",
                retain_improve_add="retain",
                notes="Preserve existing section; clarify answer density.",
            )
        )
        seen_heads.add(h.text.lower())

    if not listing_index:
        for row in section_candidates[:6]:
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
                    notes=(
                        f"On-topic probe with page_coverage={row.page_coverage}; "
                        f"write a direct answer using page facts only."
                    ),
                )
            )

    questions: list[str] = []
    q_source = brand_nav if listing_index else section_candidates
    for row in q_source:
        q = row.query_text.strip()
        if not q.endswith("?"):
            q = q + "?"
        if q not in questions:
            questions.append(q)
    if not listing_index:
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
            if p and str(p) not in entities:
                entities.append(str(p))
    if brand and brand not in entities:
        entities.insert(0, brand)
    entities = entities[:12]

    faq_suggestions = [
        {
            "question": q,
            "answer_guidance": (
                "Listing: answer with brand + link to best article — do not invent long FAQ blocks."
                if listing_index
                else "Answer in 2–4 sentences using only known page/site facts."
            ),
        }
        for q in questions[:5]
    ]

    schema_suggestions: list[str] = []
    types = set((page.structured_data or {}).get("types") or [])
    if listing_index:
        if "Organization" not in types:
            schema_suggestions.append("Organization")
        if "Blog" not in types and "WebSite" not in types:
            schema_suggestions.append("WebSite")
    else:
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
            {
                "url": link["url"],
                "anchor": link.get("anchor") or link["url"],
                "action": "retain" if not listing_index else "expand",
            }
        )

    matrix = [
        {
            "query_id": r.query_id,
            "query_text": r.query_text,
            "intent": r.intent,
            "page_coverage": r.page_coverage,
            "best_page_url": r.best_page_url,
            "note": r.note,
            "fits_this_page": (
                False
                if listing_index
                else _query_fits_article_page(r, page)
            ),
            "listing_index_page": listing_index,
            "not_ai_visibility": True,
            "not_health_v1": True,
        }
        for r in gap_report.coverage_by_query
    ]

    edit_ops = _build_edit_ops(
        page,
        outline,
        gap_report,
        listing_index=listing_index,
        coverage_by_id=coverage_by_id,
    )

    # Article pages: explicit best_page routing for uncovered off-topic probes
    # (not added to outline — must still surface as cross_page_link, not silence).
    if not listing_index:
        gaps_map = _gap_by_id(gap_report)
        for row in uncovered:
            if _query_fits_article_page(row, page):
                continue
            linked = _gap_ids_for_queries(
                gap_report, [row.query_id], limit=2
            ) or _fallback_gap_ids(gap_report, limit=1)
            if not linked:
                continue
            g = gaps_map.get(linked[0])
            best = (g.best_page_url if g else None) or row.best_page_url
            edit_ops.append(
                ContentChange(
                    action="add",
                    target="cross_page_link",
                    reason=_reason_for_gap(
                        base=(
                            "Probe is off-topic for this article — link to best_page "
                            f"({best or 'choose matching article'}) instead of adding "
                            "a thin answer section here"
                        ),
                        query_text=row.query_text,
                        gap=g,
                    ),
                    related_query_ids=[row.query_id],
                    related_gap_ids=linked,
                )
            )

    work_queue = [
        e for e in edit_ops if e.action in ("add", "rewrite", "expand", "remove")
    ]
    # Cap section farms; listing already has zero section: adds
    add_sections = [w for w in work_queue if w.target.startswith("section:")]
    other_work = [w for w in work_queue if not w.target.startswith("section:")]
    # Prefer at most one cross_page_link cluster
    cross = [w for w in other_work if w.target == "cross_page_link"]
    other_non_cross = [w for w in other_work if w.target != "cross_page_link"]
    work_queue = other_non_cross + cross[:3] + add_sections[:4]
    # Final hard filter
    work_queue = [w for w in work_queue if w.related_gap_ids]

    meta = page.meta_description
    if not meta:
        meta = f"{primary}."
        if brand:
            meta = f"{primary} — {brand}."
        meta = meta[:155]
    title = page.title or primary
    if brand and brand.lower() not in (title or "").lower() and len(title) < 45:
        title = f"{title} | {brand}"

    qs_id = None
    if isinstance(queryset, dict):
        qs_id = queryset.get("query_set_id")
    elif hasattr(queryset, "query_set_id"):
        qs_id = getattr(queryset, "query_set_id")

    n_gaps = len(gap_report.gaps)
    n_uncovered = len(uncovered)
    exec_summary = (
        f"Page '{primary}' has {n_gaps} content gaps "
        f"({n_uncovered} under-covered probes vs {gap_report.query_set_version}). "
    )
    if listing_index:
        exec_summary += (
            "Listing/index genre gate: recommend H1/brand/schema/internal links — "
            "not per-query article answer sections. "
        )
    exec_summary += (
        "Page intelligence = extractable answer units; queryset matrix = page_coverage only — "
        "not AI visibility and not health-v1."
    )

    genre_guidance = list(_GENRE_FORMAT_GUIDANCE.get(str(genre), []))
    if listing_index:
        genre_guidance = [
            "Index/listing: one H1, preferred brand in titles/lead/Organization schema, "
            "sequential h2→h3, link to best_page articles.",
            "Do not add thin per-query answer sections on the homepage.",
        ] + genre_guidance
    if not genre_guidance:
        genre_guidance = [
            "Apply Researcher taxonomy uniformly; lean formats by genre when known "
            "(SaaS compare/pricing/HowTo; Docs defs/steps; Blog tutorials; Ecommerce specs/PDP)."
        ]

    gap_catalog = dict(gap_report.gap_catalog_by_taxonomy or {})

    has_missing_faq = any((g.kind or "") == "missing_faq" for g in gap_report.gaps)
    has_no_answer_block = any(g.gap_type == "no_answer_block" for g in gap_report.gaps)
    brief_action: BriefAction = "expand_section"
    if listing_index and any(g.gap_type == "schema_gap" for g in gap_report.gaps):
        brief_action = "add_schema"
    elif listing_index and any(g.gap_type == "entity_mismatch" for g in gap_report.gaps):
        brief_action = "clarify_entity"
    elif has_missing_faq and not listing_index:
        brief_action = "add_faq"
    elif any(g.gap_type == "schema_gap" for g in gap_report.gaps):
        brief_action = "add_schema"
    elif has_no_answer_block and not listing_index:
        brief_action = "add_howto"
    elif any(g.gap_type == "entity_mismatch" for g in gap_report.gaps):
        brief_action = "clarify_entity"
    elif page.word_count < 40 and n_uncovered > 2 and not listing_index:
        brief_action = "create_page"

    sheet_edit_ops: list[EditOp] = [
        c.to_edit_op(idx=i) for i, c in enumerate(edit_ops) if c.related_gap_ids
    ]
    section_ops = [
        e for e in sheet_edit_ops if (e.target_locator or e.anchor_locator or "").startswith("section:")
        or (e.anchor_locator or "").startswith("section:")
    ]
    other_ops = [e for e in sheet_edit_ops if e not in section_ops]
    # Reconstruct without relying on object identity
    section_ops = [
        e
        for e in sheet_edit_ops
        if str(e.target_locator or "").startswith("section:")
        or str(e.anchor_locator or "").startswith("section:")
    ]
    other_ops = [
        e
        for e in sheet_edit_ops
        if not str(e.target_locator or "").startswith("section:")
        and not str(e.anchor_locator or "").startswith("section:")
    ]
    sheet_edit_ops = other_ops + (section_ops[:4] if not listing_index else [])

    target_qids = sorted(
        {
            qid
            for g in gap_report.gaps
            for qid in (g.query_ids or ([g.query_id] if g.query_id else []))
        }
    )
    answer_shape = None
    if brief_action == "add_faq":
        answer_shape = "faq"
    elif brief_action == "add_howto":
        answer_shape = "steps"
    elif any(u.kind == "definition" for u in page.answer_units):
        answer_shape = "definition"

    brief_id = "brief_" + hashlib.sha1(
        f"{page.url}|{qs_id}|{brief_action}|{n_gaps}|listing={listing_index}".encode()
    ).hexdigest()[:12]

    warnings: list[str] = []
    if listing_index:
        warnings.append(
            "listing_index_genre_gate: suppressed per-query section:add thin probes on homepage/index"
        )

    return ContentOptimizationBrief(
        brief_version=BRIEF_VERSION,
        schema_version=BRIEF_VERSION,
        brief_id=brief_id,
        gap_ids=[g.gap_id or g.id for g in gap_report.gaps],
        target_query_ids=target_qids,
        action=brief_action,
        target_url=page.url or None,
        outline=[o.heading for o in outline],
        must_include_entities=list(entities),
        must_include_answer_shape=answer_shape,  # type: ignore[arg-type]
        provenance_notes="derived from gap+page-intel; not a ranking promise",
        priority=float(min(1.0, 0.2 + 0.1 * n_uncovered)),
        edit_ops=sheet_edit_ops,
        legacy_edit_ops=[c for c in edit_ops if c.related_gap_ids],
        success_criteria=[
            "one_strong_answer_unit_per_important_probe",
            "page_coverage_improved_without_visibility_claim",
            "no_thin_page_farm_per_query",
            "work_queue_items_cite_related_gap_ids",
        ],
        page_url=page.url,
        scope={
            "methodology": CONTENT_OPTIMIZATION_METHODOLOGY,
            "page_intel_version": PAGE_INTEL_VERSION,
            "gap_version": GAP_VERSION,
            "brief_version": BRIEF_VERSION,
            "query_set_version": gap_report.query_set_version,
            "query_set_id": qs_id,
            "hostname": page.hostname,
            "target_match_scope": page.target_match_scope,
            "site_genre": genre,
            "listing_index_page": listing_index,
            "generate_draft": bool(cfg.get("generate_draft", False)),
            "draft_paid": bool(cfg.get("draft_paid", False)),
            "content_draft": bool(
                cfg.get("content_draft", cfg.get("generate_draft", False))
            ),
            "page_vs_queryset": {
                "page_intelligence": "extractable_answer_units",
                "queryset": "frozen_probes_x_page_coverage",
                "coverage_is_not_ai_visibility": True,
                "coverage_is_not_health_v1": True,
            },
        },
        executive_summary=exec_summary,
        answerability={
            **dict(page.answerability_signals or {}),
            "answer_unit_count": len(page.answer_units),
            "answer_unit_kinds": sorted({u.kind for u in page.answer_units}),
        },
        gap_catalog=gap_catalog,
        gap_catalog_ids=[g.gap_id or g.id for g in gap_report.gaps],
        query_content_matrix=matrix,
        work_queue=work_queue,
        proposed_title=title[:70],
        proposed_meta_description=meta[:160],
        proposed_h1=(brand or primary)[:120] if listing_index and not page.h1 else primary[:120],
        outline_sections=outline,
        retain=retain,
        improve=improve,
        add=add,
        questions_to_answer=questions,
        entities_to_cover=entities,
        faq_suggestions=faq_suggestions,
        schema_suggestions=schema_suggestions,
        internal_link_suggestions=link_suggestions,
        genre_format_guidance=genre_guidance,
        do_principles=list(DO_PRINCIPLES),
        aeo_writing_requirements=list(AEO_WRITING_REQUIREMENTS),
        caveats=list(CAVEATS),
        anti_patterns=list(ANTI_PATTERNS),
        input_citations={
            "page_intel_version": PAGE_INTEL_VERSION,
            "gap_report_version": gap_report.gap_report_version
            or gap_report.schema_version,
            "query_set_version": gap_report.query_set_version,
            "query_set_id": qs_id,
            "page_url": page.url,
            "gap_count": n_gaps,
            "site_profile_present": bool(site_profile),
            "listing_index_page": listing_index,
            "researcher_taxonomy": [label for _, label in RESEARCHER_GAP_TAXONOMY],
        },
        method="deterministic_brief_v1",
        warnings=warnings,
    )
