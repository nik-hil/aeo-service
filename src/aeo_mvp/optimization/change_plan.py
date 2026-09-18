"""Deterministic change plan: retain | rewrite | expand | remove | add."""

from __future__ import annotations

from aeo_mvp.optimization.models import (
    ChangePlanItem,
    ContentGapReport,
    ContentOptimizationBrief,
    PageIntelligence,
)


def build_change_plan(
    page: PageIntelligence,
    brief: ContentOptimizationBrief,
    gap_report: ContentGapReport,
) -> list[ChangePlanItem]:
    """Pure function — stable order by action then target."""
    items: list[ChangePlanItem] = []
    gap_by_cat = {}
    for g in gap_report.gaps:
        gap_by_cat.setdefault(g.category, []).append(g)

    if page.h1 and brief.proposed_h1 and page.h1.strip() == brief.proposed_h1.strip():
        items.append(
            ChangePlanItem(
                action="retain",
                target="h1",
                reason="Existing H1 already matches brief primary topic",
                related_gap_ids=[],
            )
        )
    elif brief.proposed_h1:
        items.append(
            ChangePlanItem(
                action="rewrite" if page.h1 else "add",
                target="h1",
                reason="Align H1 with proposed answer topic",
                related_gap_ids=[g.id for g in gap_by_cat.get("metadata", []) if "h1" in g.id],
            )
        )

    if page.title and brief.proposed_title and page.title != brief.proposed_title:
        items.append(
            ChangePlanItem(
                action="rewrite",
                target="title",
                reason="Update title toward brief proposal",
                related_gap_ids=[g.id for g in gap_by_cat.get("metadata", []) if "title" in g.id],
            )
        )
    elif not page.title and brief.proposed_title:
        items.append(
            ChangePlanItem(
                action="add",
                target="title",
                reason="Document title missing",
                related_gap_ids=[g.id for g in gap_by_cat.get("metadata", [])],
            )
        )
    elif page.title:
        items.append(
            ChangePlanItem(
                action="retain",
                target="title",
                reason="Title acceptable",
            )
        )

    if not page.meta_description:
        items.append(
            ChangePlanItem(
                action="add",
                target="meta_description",
                reason="Meta description missing",
                related_gap_ids=[g.id for g in gap_by_cat.get("metadata", []) if "meta" in g.id],
            )
        )
    else:
        items.append(
            ChangePlanItem(
                action="expand",
                target="meta_description",
                reason="Improve meta toward answer-first summary",
            )
        )

    if page.word_count < 200:
        items.append(
            ChangePlanItem(
                action="expand",
                target="body",
                reason=f"Thin body (word_count={page.word_count})",
                related_gap_ids=[g.id for g in gap_by_cat.get("section", [])],
                related_query_ids=[
                    r.query_id
                    for r in gap_report.query_coverage
                    if r.coverage in ("none", "mention")
                ][:6],
            )
        )
    else:
        items.append(
            ChangePlanItem(
                action="retain",
                target="body_core",
                reason="Core body length adequate; refine sections per outline",
            )
        )

    for section in brief.outline:
        if section.retain_improve_add == "add":
            items.append(
                ChangePlanItem(
                    action="add",
                    target=f"section:{section.heading}",
                    reason=section.notes or "Add outline section for uncovered demand",
                    related_query_ids=list(section.related_query_ids),
                    related_gap_ids=[g.id for g in gap_by_cat.get("query", [])][:3],
                )
            )
        elif section.retain_improve_add == "improve":
            items.append(
                ChangePlanItem(
                    action="rewrite",
                    target=f"section:{section.heading}",
                    reason=section.notes or "Improve answer density",
                    related_query_ids=list(section.related_query_ids),
                )
            )

    if brief.faq_suggestions:
        items.append(
            ChangePlanItem(
                action="add",
                target="faq",
                reason="Add FAQ pairs mirroring brief questions",
                related_gap_ids=[g.id for g in gap_by_cat.get("qa", [])],
            )
        )

    for schema in brief.schema_suggestions:
        items.append(
            ChangePlanItem(
                action="add",
                target=f"schema:{schema}",
                reason=f"Add {schema} JSON-LD mirroring visible content only",
                related_gap_ids=[g.id for g in gap_by_cat.get("structured_data", [])],
            )
        )

    # Stable order
    action_order = {"retain": 0, "rewrite": 1, "expand": 2, "remove": 3, "add": 4}
    items.sort(key=lambda i: (action_order[i.action], i.target.lower()))
    return items
