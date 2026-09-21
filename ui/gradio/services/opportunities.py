"""Biggest Opportunities — deterministic ordering from existing report fields.

Ordering rule (documented; do not invent scores):
1. Recommendations from ``report["recommendations"]``, sorted by:
   - ``rank`` ascending when present (None ranks last)
   - then ``priority_score`` descending
   - then ``code`` ascending (stable tie-break)
2. Content-gap rows (flattened from ``content_gaps[*].gaps``) with severity in
   {critical, high, medium}, sorted by severity_rank then ``gap_id``, that are
   not already represented by a recommendation's ``affected_urls`` for the same
   ``best_page_url`` / page, appended next.
3. Cap at ``limit`` (default 8).

Selecting an opportunity opens page detail for its primary URL when available.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from services.formatters import severity_rank


@dataclass(frozen=True)
class Opportunity:
    kind: str  # recommendation | content_gap
    id: str
    title: str
    summary: str
    page_url: str | None
    severity_or_effort: str
    sort_key: tuple


def _rec_sort_key(rec: dict[str, Any]) -> tuple:
    rank = rec.get("rank")
    try:
        rank_n = int(rank) if rank is not None else 10_000
    except (TypeError, ValueError):
        rank_n = 10_000
    try:
        priority = float(rec.get("priority_score") or 0.0)
    except (TypeError, ValueError):
        priority = 0.0
    code = str(rec.get("code") or rec.get("id") or "")
    return (0, rank_n, -priority, code)


def _gap_items(report: dict[str, Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for block in report.get("content_gaps") or []:
        if not isinstance(block, dict):
            continue
        page_url = block.get("page_url")
        for gap in block.get("gaps") or []:
            if not isinstance(gap, dict):
                continue
            item = dict(gap)
            item.setdefault("best_page_url", page_url)
            item["_page_url"] = item.get("best_page_url") or page_url
            out.append(item)
    return out


def build_opportunities(report: dict[str, Any] | None, *, limit: int = 8) -> list[Opportunity]:
    if not report:
        return []

    covered_urls: set[str] = set()
    items: list[Opportunity] = []

    recs = [r for r in (report.get("recommendations") or []) if isinstance(r, dict)]
    recs_sorted = sorted(recs, key=_rec_sort_key)
    for rec in recs_sorted:
        urls = [u for u in (rec.get("affected_urls") or []) if isinstance(u, str)]
        page_url = urls[0] if urls else None
        for u in urls:
            covered_urls.add(u)
        oid = str(rec.get("id") or rec.get("code") or "")
        title = str(rec.get("title") or rec.get("code") or "Recommendation")
        summary = str(
            rec.get("problem")
            or rec.get("recommended_action")
            or rec.get("rationale")
            or ""
        )
        effort = str(rec.get("effort") or "—")
        items.append(
            Opportunity(
                kind="recommendation",
                id=oid,
                title=title,
                summary=summary,
                page_url=page_url,
                severity_or_effort=f"effort {effort}",
                sort_key=_rec_sort_key(rec),
            )
        )

    gaps = _gap_items(report)
    eligible = []
    for gap in gaps:
        sev = str(gap.get("severity") or "").lower()
        if sev not in {"critical", "high", "medium"}:
            continue
        page_url = gap.get("_page_url")
        if isinstance(page_url, str) and page_url in covered_urls:
            continue
        eligible.append(gap)

    eligible.sort(
        key=lambda g: (
            1,
            severity_rank(str(g.get("severity"))),
            str(g.get("gap_id") or g.get("query_id") or ""),
        )
    )
    for gap in eligible:
        page_url = gap.get("_page_url") if isinstance(gap.get("_page_url"), str) else None
        oid = str(gap.get("gap_id") or gap.get("query_id") or "")
        gtype = str(gap.get("gap_type") or "gap")
        title = f"Content gap: {gtype}"
        summary = str(gap.get("rationale") or gap.get("explanation") or "")
        items.append(
            Opportunity(
                kind="content_gap",
                id=oid,
                title=title,
                summary=summary,
                page_url=page_url,
                severity_or_effort=str(gap.get("severity") or ""),
                sort_key=(
                    1,
                    severity_rank(str(gap.get("severity"))),
                    oid,
                ),
            )
        )

    return items[: max(0, int(limit))]


def opportunities_table(rows: list[Opportunity]) -> list[list[str]]:
    table: list[list[str]] = []
    for i, row in enumerate(rows, start=1):
        table.append(
            [
                str(i),
                row.kind,
                row.title,
                (row.summary or "")[:160],
                row.page_url or "—",
                row.severity_or_effort,
            ]
        )
    return table


def opportunity_as_dict(row: Opportunity) -> dict[str, Any]:
    return asdict(row)


def resolve_opportunity_page_url(
    opportunities: list[Any],
    choice: str | None,
    *,
    fallback: str | None = None,
) -> str | None:
    """Map dropdown choice → page URL; stable when page_url is missing."""
    if not choice or not opportunities:
        return fallback
    try:
        idx = int(str(choice).split(".", 1)[0]) - 1
    except ValueError:
        return fallback
    if idx < 0 or idx >= len(opportunities):
        return fallback
    row = opportunities[idx]
    if isinstance(row, Opportunity):
        return row.page_url or fallback
    if isinstance(row, dict):
        url = row.get("page_url")
        return url if isinstance(url, str) and url else fallback
    return fallback

