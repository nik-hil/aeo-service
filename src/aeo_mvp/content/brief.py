"""opt-brief-v1 — deterministic ContentOptimizationBrief (zero LLM)."""

from __future__ import annotations

from typing import Any

from aeo_mvp.content.models import (
    BRIEF_VERSION,
    CONTENT_OPTIMIZATION_METHODOLOGY,
    DRAFT_VERSION,
    GAP_VERSION,
    PAGE_INTEL_VERSION,
    RESEARCHER_GAP_TAXONOMY,
    BriefAction,
    ContentChange,
    ContentGapReport,
    ContentOptimizationBrief,
    EditOp,
    OutlineSection,
    PageIntelligence,
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
    "One strong answer unit per important probe — not thin page farms.",
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
    ],
    "ecommerce": [
        "Prefer specs / PDP structured units for ecommerce probes.",
        "Same taxonomy — format + entity/identity + media when helpful.",
    ],
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


def _gap_ids_for_types(
    gap_by_type: dict[str, list[str]], *types: str, limit: int = 3
) -> list[str]:
    """Collect gap ids for sheet types (and legacy aliases) in priority order."""
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
    """Link work-queue items to gaps that cite the same query ids."""
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


def _build_edit_ops(
    page: PageIntelligence,
    brief_outline: list[OutlineSection],
    gap_report: ContentGapReport,
) -> list[ContentChange]:
    items: list[ContentChange] = []
    gap_by_type: dict[str, list[str]] = {}
    for g in gap_report.gaps:
        gid = g.id or g.gap_id
        if gid:
            gap_by_type.setdefault(g.gap_type, []).append(gid)
            # Retain legacy short-label buckets when kind was set (compat).
            if g.kind:
                gap_by_type.setdefault(g.kind, []).append(gid)

    schema_gap_ids = _gap_ids_for_types(
        gap_by_type, "schema_gap", "metadata", limit=2
    )

    if page.h1:
        items.append(
            ContentChange(
                action="retain",
                target="h1",
                reason="Existing H1 present",
            )
        )
    else:
        items.append(
            ContentChange(
                action="add",
                target="h1",
                reason="H1 missing",
                related_gap_ids=schema_gap_ids,
            )
        )

    if not page.meta_description:
        items.append(
            ContentChange(
                action="add",
                target="meta_description",
                reason="Meta description missing",
                related_gap_ids=schema_gap_ids,
            )
        )
    else:
        items.append(
            ContentChange(
                action="expand",
                target="meta_description",
                reason="Improve toward answer-first summary",
                related_gap_ids=_gap_ids_for_types(
                    gap_by_type, "thin_coverage", "structure_gap", "structure", limit=2
                ),
            )
        )

    if page.word_count < 200:
        thin_qids = [
            r.query_id
            for r in gap_report.coverage_by_query
            if r.page_coverage in ("absent", "thin", "mismatched")
        ][:6]
        items.append(
            ContentChange(
                action="expand",
                target="body",
                reason=f"Thin body (word_count={page.word_count})",
                related_gap_ids=_gap_ids_for_types(
                    gap_by_type,
                    "structure_gap",
                    "thin_coverage",
                    "structure",
                    limit=3,
                )
                or _gap_ids_for_queries(gap_report, thin_qids, limit=3),
                related_query_ids=thin_qids,
            )
        )
    else:
        items.append(
            ContentChange(
                action="retain",
                target="body_core",
                reason="Core body length adequate; refine per outline",
            )
        )

    for section in brief_outline:
        qids = list(section.related_query_ids)
        linked = _gap_ids_for_queries(gap_report, qids) or _gap_ids_for_types(
            gap_by_type,
            "thin_coverage",
            "missing_page",
            "question_coverage_gap",
            "query",
            limit=3,
        )
        if section.retain_improve_add == "add":
            items.append(
                ContentChange(
                    action="add",
                    target=f"section:{section.heading}",
                    reason=section.notes or "Add outline section for uncovered demand",
                    related_query_ids=qids,
                    related_gap_ids=linked,
                )
            )
        elif section.retain_improve_add == "improve":
            items.append(
                ContentChange(
                    action="rewrite",
                    target=f"section:{section.heading}",
                    reason=section.notes or "Improve answer density",
                    related_query_ids=qids,
                    related_gap_ids=linked,
                )
            )

    action_order = {"retain": 0, "rewrite": 1, "expand": 2, "remove": 3, "add": 4}
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

    uncovered = [
        r
        for r in gap_report.coverage_by_query
        if r.page_coverage in ("absent", "thin", "mismatched")
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

    outline: list[OutlineSection] = [
        OutlineSection(
            heading=primary,
            level=1,
            intent="informational",
            retain_improve_add="improve" if page.h1 else "add",
            related_query_ids=[r.query_id for r in uncovered[:2]],
            notes="Answer-first introduction grounded in page topic.",
        )
    ]
    seen_heads = {primary.lower()}
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
                notes=f"page_coverage was {row.page_coverage}; write a direct answer.",
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
            if p and str(p) not in entities:
                entities.append(str(p))
    entities = entities[:12]

    faq_suggestions = [
        {
            "question": q,
            "answer_guidance": "Answer in 2–4 sentences using only known page/site facts.",
        }
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

    matrix = [
        {
            "query_id": r.query_id,
            "query_text": r.query_text,
            "intent": r.intent,
            "page_coverage": r.page_coverage,
            "note": r.note,
            # Honesty: this cell is page coverage, not AI visibility / health
            "not_ai_visibility": True,
            "not_health_v1": True,
        }
        for r in gap_report.coverage_by_query
    ]

    edit_ops = _build_edit_ops(page, outline, gap_report)
    # Work queue: prioritize one strong unit per important under-covered probe (no thin farms)
    work_queue = [e for e in edit_ops if e.action in ("add", "rewrite", "expand", "remove")]
    # Cap add-section ops to avoid thin-page-per-query farms
    add_sections = [w for w in work_queue if w.target.startswith("section:")]
    other_work = [w for w in work_queue if not w.target.startswith("section:")]
    work_queue = other_work + add_sections[:6]

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
        "Page intelligence = extractable answer units; queryset matrix = page_coverage only — "
        "not AI visibility and not health-v1."
    )

    genre_guidance = list(_GENRE_FORMAT_GUIDANCE.get(str(genre), []))
    if not genre_guidance:
        genre_guidance = [
            "Apply Researcher taxonomy uniformly; lean formats by genre when known "
            "(SaaS compare/pricing/HowTo; Docs defs/steps; Blog tutorials; Ecommerce specs/PDP)."
        ]

    gap_catalog = dict(gap_report.gap_catalog_by_taxonomy or {})

    # Map primary BriefAction from dominant gaps (deterministic; no thin farms).
    # P1-2: add_faq from canonical kind=missing_faq and/or gap_type=no_answer_block.
    has_missing_faq = any((g.kind or "") == "missing_faq" for g in gap_report.gaps)
    has_no_answer_block = any(g.gap_type == "no_answer_block" for g in gap_report.gaps)
    brief_action: BriefAction = "expand_section"
    if has_missing_faq:
        brief_action = "add_faq"
    elif any(g.gap_type == "schema_gap" for g in gap_report.gaps):
        brief_action = "add_schema"
    elif has_no_answer_block:
        brief_action = "add_howto"
    elif any(g.gap_type == "entity_mismatch" for g in gap_report.gaps):
        brief_action = "clarify_entity"
    elif page.word_count < 40 and n_uncovered > 2:
        brief_action = "create_page"

    sheet_edit_ops: list[EditOp] = [c.to_edit_op(idx=i) for i, c in enumerate(edit_ops)]
    section_ops = [
        e for e in sheet_edit_ops if (e.target_locator or "").startswith("section:")
    ]
    other_ops = [
        e for e in sheet_edit_ops if not (e.target_locator or "").startswith("section:")
    ]
    sheet_edit_ops = other_ops + section_ops[:6]

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

    import hashlib

    brief_id = "brief_" + hashlib.sha1(
        f"{page.url}|{qs_id}|{brief_action}|{n_gaps}".encode()
    ).hexdigest()[:12]

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
        legacy_edit_ops=list(edit_ops),
        success_criteria=[
            "one_strong_answer_unit_per_important_probe",
            "page_coverage_improved_without_visibility_claim",
            "no_thin_page_farm_per_query",
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
        proposed_h1=primary[:120],
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
            "researcher_taxonomy": [label for _, label in RESEARCHER_GAP_TAXONOMY],
        },
        method="deterministic_brief_v1",
        warnings=[],
    )
