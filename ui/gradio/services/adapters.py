"""DTO adapters: API report/pages → UI view models. No scoring."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from services.enrichment import EnrichmentCache
from services.formatters import (
    format_pct_rate,
    format_provenance,
    format_score,
    health_label,
    score_value,
)
from services.sanitize import escape_text, safe_markdown_paragraph, sanitize_code_block

# UI request cap for multi-page crawls. Backend hard ceiling is 25 (schemas le=25).
UI_MULTI_MAX_PAGES = 20
BACKEND_MAX_PAGES_CEILING = 25


@dataclass
class ScoreCard:
    key: str
    label: str
    value: str
    provenance: str
    glossary_key: str | None = None


@dataclass
class BeforeView:
    page_url: str
    title: str
    meta_description: str
    headings: list[str]
    answer_blocks: list[str]
    word_count: int
    markdown: str
    raw_html_code: str | None = None  # escaped fence only; optional


@dataclass
class BriefView:
    brief_id: str
    page_url: str
    action: str
    summary: str
    outline: list[str]
    work_queue: list[str]
    caveats: list[str]
    markdown: str


@dataclass
class DraftView:
    page_url: str
    status: str
    generator: str
    content_provenance: str
    label: str  # honest UI label
    disclaimer: str
    body_markdown: str
    empty: bool


@dataclass
class RecView:
    id: str
    title: str
    problem: str
    why: str
    action: str
    effort: str
    impact: Any
    evidence_snippets: list[str]
    affected_urls: list[str]


@dataclass
class EvidenceView:
    snippets: list[str]
    finding_lines: list[str]
    provenance_notes: list[str]
    caveats: list[str]
    markdown: str


@dataclass
class PageRow:
    page_id: str
    url: str
    title: str
    depth: int
    status_code: int | None
    fetch_error: str | None
    source_url: str | None = None
    content_representation: str | None = None
    canonical_url: str | None = None
    source_markdown: str | None = None


@dataclass
class OverviewVM:
    job_id: str
    base_url: str
    demo_mode: bool
    mode: str  # single | multi
    pages_crawled: int
    crawl_partial: bool
    crawl_note: str
    health: ScoreCard
    components: list[ScoreCard]
    visibility_lines: list[str]
    visibility_summary: str
    gap_count: int
    opportunity_count: int
    executive_bullets: list[str]
    caveats: list[str]


@dataclass
class PageHeaderVM:
    title: str
    url: str
    status: str
    depth: str
    markdown: str
    html: str


def _metric(scores: dict[str, Any], key: str) -> Any:
    return scores.get(key) if isinstance(scores, dict) else None


def _count_gaps(report: dict[str, Any]) -> int:
    n = 0
    for block in report.get("content_gaps") or []:
        if not isinstance(block, dict):
            continue
        gaps = block.get("gaps") or []
        if isinstance(gaps, list):
            n += sum(1 for g in gaps if isinstance(g, dict))
    return n


def adapt_overview(
    report: dict[str, Any],
    *,
    mode: str,
    opportunity_count: int | None = None,
) -> OverviewVM:
    scores = report.get("scores") or {}
    health_obj = _metric(scores, "aeo_health")
    hv = score_value(health_obj)
    health = ScoreCard(
        key="aeo_health",
        label=f"AEO Health — {health_label(hv)}",
        value=format_score(health_obj),
        provenance=format_provenance(health_obj),
        glossary_key="aeo_health",
    )
    components = [
        ScoreCard("technical", "Technical", format_score(_metric(scores, "technical")), format_provenance(_metric(scores, "technical"))),
        ScoreCard("content", "Content", format_score(_metric(scores, "content")), format_provenance(_metric(scores, "content"))),
        ScoreCard(
            "entity",
            "Entity Clarity",
            format_score(_metric(scores, "entity")),
            format_provenance(_metric(scores, "entity")),
            "entity_score",
        ),
        ScoreCard("structured_data", "Structured Data", format_score(_metric(scores, "structured_data")), format_provenance(_metric(scores, "structured_data"))),
        ScoreCard("answerability", "Answerability", format_score(_metric(scores, "answerability")), format_provenance(_metric(scores, "answerability"))),
    ]

    visibility_lines: list[str] = []
    visibility_summary = "—"
    exp = report.get("experiment") or {}
    if isinstance(exp, dict) and exp:
        kind = escape_text(exp.get("experiment_kind") or "—")
        provider = escape_text(exp.get("provider_name") or "—")
        visibility_lines.append(f"Experiment: **{kind}** via {provider}")
        visibility_lines.append(
            f"Consumer UI ranking measured: **{'yes' if exp.get('measures_consumer_ui') else 'no'}**"
        )
        primary_rate = None
        for key, label in (
            ("llm_mention_rate", "LLM mention rate"),
            ("llm_url_mention_rate", "LLM URL mention rate"),
            ("ai_search_mention_rate", "AI search mention rate"),
            ("ai_search_citation_rate", "AI search citation rate"),
            ("query_coverage", "Query coverage"),
        ):
            if key in exp:
                rate = format_pct_rate(exp.get(key))
                visibility_lines.append(
                    f"{label}: **{rate}** "
                    f"(provenance {format_provenance(exp.get(key))})"
                )
                if primary_rate is None:
                    primary_rate = rate
        visibility_summary = primary_rate or str(exp.get("experiment_kind") or "sample")

    exec_sum = report.get("executive_summary") or {}
    bullets: list[str] = []
    if isinstance(exec_sum, dict):
        for key in ("strongest_areas", "weakest_areas", "top_3_actions"):
            vals = exec_sum.get(key) or []
            if isinstance(vals, list) and vals:
                bullets.append(f"**{key.replace('_', ' ').title()}:** " + "; ".join(escape_text(v) for v in vals[:5]))

    caveats = [escape_text(c) for c in (report.get("caveats") or []) if c][:8]

    crawl = report.get("crawl") or (report.get("methodology") or {}).get("crawl") or {}
    crawl_partial = False
    crawl_note = ""
    if isinstance(crawl, dict):
        status = str(crawl.get("status") or "")
        discovered = crawl.get("discovered")
        fetched = crawl.get("fetched")
        errors = crawl.get("errors")
        if status and status not in {"completed", "ok", "success", ""}:
            crawl_partial = True
        if isinstance(errors, int) and errors > 0:
            crawl_partial = True
        if (
            isinstance(discovered, int)
            and isinstance(fetched, int)
            and discovered > 0
            and fetched < discovered
        ):
            crawl_partial = True
        if crawl_partial:
            crawl_note = (
                f"Partial crawl signal: status={escape_text(status)}, "
                f"discovered={discovered}, fetched={fetched}, errors={errors}"
            )

    gap_count = _count_gaps(report)
    opp_n = int(opportunity_count) if opportunity_count is not None else 0

    return OverviewVM(
        job_id=str(report.get("job_id") or ""),
        base_url=str(report.get("base_url") or ""),
        demo_mode=bool(report.get("demo_mode")),
        mode=mode,
        pages_crawled=int(report.get("pages_crawled") or 0),
        crawl_partial=crawl_partial,
        crawl_note=crawl_note,
        health=health,
        components=components,
        visibility_lines=visibility_lines,
        visibility_summary=visibility_summary,
        gap_count=gap_count,
        opportunity_count=opp_n,
        executive_bullets=bullets,
        caveats=caveats,
    )


def adapt_pages(pages_payload: dict[str, Any] | None) -> list[PageRow]:
    if not pages_payload:
        return []
    rows: list[PageRow] = []
    for p in pages_payload.get("pages") or []:
        if not isinstance(p, dict):
            continue
        rows.append(
            PageRow(
                page_id=str(p.get("id") or ""),
                url=str(p.get("url") or ""),
                title=str(p.get("title") or ""),
                depth=int(p.get("depth") or 0),
                status_code=p.get("status_code"),
                fetch_error=p.get("fetch_error"),
                source_url=p.get("source_url"),
                content_representation=p.get("content_representation"),
                canonical_url=p.get("canonical_url"),
                source_markdown=p.get("source_markdown"),
            )
        )
    return rows


def truncate_url(url: str, *, max_len: int = 64) -> str:
    """Readable truncation for dense 20-page tables (full URL remains in selector)."""
    u = url or ""
    if len(u) <= max_len:
        return u
    head = max(20, max_len // 2 - 2)
    tail = max(12, max_len - head - 1)
    return f"{u[:head]}…{u[-tail:]}"


def pages_table(rows: list[PageRow]) -> list[list[str]]:
    return [
        [
            (r.title or "(untitled)")[:80],
            truncate_url(r.url),
            str(r.depth),
            str(r.status_code if r.status_code is not None else "—"),
            (r.fetch_error or "")[:60],
        ]
        for r in rows
    ]


def _page_row_for(
    pages_payload: dict[str, Any] | None, page_url: str | None
) -> PageRow | None:
    if not pages_payload or not page_url:
        return None
    target = _normalize_url(page_url)
    for p in adapt_pages(pages_payload):
        candidates = [
            p.url,
            p.source_url,
            p.canonical_url,
            (p.source_url or "").removesuffix(".md") if p.source_url else None,
        ]
        if any(_normalize_url(c) == target for c in candidates if c):
            return p
    return None


def page_header(
    report: dict[str, Any] | None,
    pages_payload: dict[str, Any] | None,
    page_url: str | None,
) -> PageHeaderVM:
    """Clear page-detail header: title, URL, status, depth."""
    url = page_url or (str(report.get("base_url")) if report else "") or ""
    title = ""
    status = "—"
    depth = "—"
    row = _page_row_for(pages_payload, page_url or url)
    if row:
        title = (row.title or "").strip()
        status = str(row.status_code if row.status_code is not None else "—")
        if row.fetch_error:
            status = f"{status} / error"
        depth = str(row.depth)
        url = row.url or url
    if not title and report:
        pi = _page_intelligence_for(report, page_url)
        title = str((pi or {}).get("title") or "").strip()
    # Prefer real extracted title — avoid "(untitled)" when title exists upstream.
    if not title:
        title = "(untitled)"
    html = (
        f'<div class="aeo-page-header">'
        f'<div class="aeo-page-title">{escape_text(title)}</div>'
        f'<div class="aeo-page-url">{escape_text(url) or "—"}</div>'
        f'<div class="aeo-page-meta">'
        f"<span>Status: <strong>{escape_text(status)}</strong></span>"
        f"<span>Depth: <strong>{escape_text(depth)}</strong></span>"
        f"</div></div>"
    )
    md = (
        f"**{escape_text(title)}** · {escape_text(url) or '—'} · "
        f"status {escape_text(status)} · depth {escape_text(depth)}"
    )
    return PageHeaderVM(title=title, url=url, status=status, depth=depth, markdown=md, html=html)


def _normalize_url(u: str | None) -> str:
    return (u or "").rstrip("/")


def _page_intelligence_for(report: dict[str, Any], page_url: str | None) -> dict[str, Any]:
    pi = report.get("page_intelligence")
    if isinstance(pi, dict):
        if not page_url or _normalize_url(pi.get("url")) == _normalize_url(page_url):
            return pi
    # Multi-page: page_intelligence is primary only — return empty for mismatch
    if page_url and isinstance(pi, dict) and _normalize_url(pi.get("url")) != _normalize_url(page_url):
        return {}
    return pi if isinstance(pi, dict) else {}


def _source_markdown_for(
    report: dict[str, Any],
    page_url: str | None,
    pages_payload: dict[str, Any] | None = None,
) -> str | None:
    pi = _page_intelligence_for(report, page_url)
    sm = pi.get("source_markdown") if isinstance(pi, dict) else None
    if isinstance(sm, str) and sm.strip():
        return sm
    row = _page_row_for(pages_payload, page_url)
    if row and row.source_markdown and str(row.source_markdown).strip():
        return str(row.source_markdown)
    return None


def adapt_before(
    report: dict[str, Any],
    *,
    page_url: str | None = None,
    page_intel_override: dict[str, Any] | None = None,
    raw_html: str | None = None,
    pages_payload: dict[str, Any] | None = None,
) -> BeforeView:
    pi = page_intel_override if page_intel_override is not None else _page_intelligence_for(report, page_url)
    row = _page_row_for(pages_payload, page_url)
    url = str((pi.get("url") if pi else None) or (row.url if row else None) or page_url or report.get("base_url") or "")
    title = str((pi or {}).get("title") or (row.title if row else "") or "").strip()
    meta = str((pi or {}).get("meta_description") or "")
    headings = [str(h) for h in ((pi or {}).get("heading_outline") or [])][:20]
    if not headings:
        for h in (pi or {}).get("headings") or []:
            if isinstance(h, dict) and h.get("text"):
                headings.append(str(h["text"]))
            elif isinstance(h, str):
                headings.append(h)
        headings = headings[:20]

    answer_blocks: list[str] = []
    for block in (pi or {}).get("answer_blocks") or []:
        if isinstance(block, dict):
            kind = block.get("kind") or block.get("type") or "block"
            text = block.get("text") or block.get("snippet") or block.get("question") or ""
            answer_blocks.append(f"[{kind}] {text}")
        else:
            answer_blocks.append(str(block))
    answer_blocks = answer_blocks[:12]
    wc = int((pi or {}).get("word_count") or 0)

    representation = str(
        (pi or {}).get("content_representation")
        or (row.content_representation if row else None)
        or "html"
    ).lower()
    source_url = str(
        (pi or {}).get("source_url") or (row.source_url if row else None) or ""
    )
    canonical_url = str(
        (pi or {}).get("canonical_url")
        or (row.canonical_url if row else None)
        or url
    )
    source_md = _source_markdown_for(report, page_url, pages_payload)
    if source_md and not wc:
        wc = len(source_md.split())

    if representation == "markdown" or source_md:
        status = str(row.status_code if row and row.status_code is not None else "—")
        lines = [
            "### CURRENT — Hashnode Markdown",
            "",
            "_Fetched Markdown representation — not a live browser render._",
            "",
            f"**Source URL:** {escape_text(source_url or url)}",
            f"**Canonical / logical article URL:** {escape_text(canonical_url)}",
            f"**Representation:** Markdown",
            f"**HTTP status:** {escape_text(status)}",
            f"**Title:** {escape_text(title) or '—'}",
            f"**Word count:** {wc}",
            "",
            "#### Current Markdown",
            "",
        ]
        if source_md:
            lines.append(sanitize_code_block(source_md, language="markdown"))
        else:
            lines.append("_Source Markdown was not preserved for this page._")
    else:
        lines = [
            "### CURRENT — observed page signals",
            "",
            "_Observed page signals — not a live browser render._",
            "",
            f"**URL:** {escape_text(url)}",
            f"**Title:** {escape_text(title) or '—'}",
            f"**Meta description:** {escape_text(meta) or '—'}",
            f"**Word count (derived):** {wc}",
            "",
            "#### Heading outline",
        ]
        if headings:
            lines.extend(f"- {escape_text(h)}" for h in headings)
        else:
            lines.append("_No heading outline in page intelligence for this page._")
        lines.append("")
        lines.append("#### Answer blocks")
        if answer_blocks:
            lines.extend(f"- {escape_text(b)}" for b in answer_blocks)
        else:
            lines.append("_No answer blocks extracted._")
        lines.append("")
        lines.append(
            "_Before / CURRENT shows observed/derived signals from the API — not a live browser render._"
        )

    raw_code = sanitize_code_block(raw_html) if raw_html else None
    return BeforeView(
        page_url=url,
        title=title,
        meta_description=meta,
        headings=headings,
        answer_blocks=answer_blocks,
        word_count=wc,
        markdown="\n".join(lines),
        raw_html_code=raw_code,
    )


def _brief_for_page(report: dict[str, Any], page_url: str | None) -> dict[str, Any] | None:
    briefs = [b for b in (report.get("optimization_briefs") or []) if isinstance(b, dict)]
    if page_url:
        for b in briefs:
            if _normalize_url(b.get("page_url") or b.get("target_url")) == _normalize_url(page_url):
                return b
    if briefs:
        return briefs[0]
    singular = report.get("brief")
    return singular if isinstance(singular, dict) else None


def adapt_brief(report: dict[str, Any], *, page_url: str | None = None) -> BriefView | None:
    brief = _brief_for_page(report, page_url)
    if not brief:
        return None
    outline_raw = brief.get("outline") or brief.get("section_order") or []
    outline: list[str] = []
    for item in outline_raw:
        if isinstance(item, dict):
            outline.append(str(item.get("heading") or item.get("title") or item))
        else:
            outline.append(str(item))
    work_queue: list[str] = []
    for w in brief.get("work_queue") or []:
        if isinstance(w, dict):
            work_queue.append(
                f"{w.get('action', 'edit')} → {w.get('target', '?')}: {w.get('reason', '')}"
            )
        else:
            work_queue.append(str(w))
    caveats = [str(c) for c in (brief.get("caveats") or brief.get("warnings") or [])][:8]
    summary = str(
        brief.get("executive_summary")
        or brief.get("action")
        or ""
    )
    if isinstance(brief.get("executive_summary"), dict):
        summary = str(
            brief["executive_summary"].get("summary")
            or brief["executive_summary"].get("text")
            or brief.get("action")
            or ""
        )

    lines = [
        "### RECOMMENDED — optimization brief",
        "",
        "_Suggested structure and actions — never labeled as a final optimized page._",
        "",
        f"**Action:** {escape_text(brief.get('action'))}",
        f"**Page:** {escape_text(brief.get('page_url') or page_url)}",
        f"**Proposed title:** {escape_text(brief.get('proposed_title') or '—')}",
        "",
        safe_markdown_paragraph(summary),
        "",
        "#### Outline",
    ]
    lines.extend(f"- {escape_text(o)}" for o in outline[:20]) if outline else lines.append("_None_")
    lines.append("")
    lines.append("#### Work queue")
    lines.extend(f"- {escape_text(w)}" for w in work_queue[:15]) if work_queue else lines.append("_None_")
    if caveats:
        lines.append("")
        lines.append("#### Caveats")
        lines.extend(f"- {escape_text(c)}" for c in caveats)

    return BriefView(
        brief_id=str(brief.get("brief_id") or ""),
        page_url=str(brief.get("page_url") or page_url or ""),
        action=str(brief.get("action") or ""),
        summary=summary,
        outline=outline,
        work_queue=work_queue,
        caveats=caveats,
        markdown="\n".join(lines),
    )


def adapt_gaps(report: dict[str, Any], *, page_url: str | None = None) -> str:
    """Render existing content-gap rows for a page — no new metrics."""
    lines: list[str] = [
        "### Content gaps ⓘ",
        "",
        "_Evidence-backed gaps vs the frozen QuerySet (content-gap-v1). "
        "Not AEO Health and not AI visibility._",
        "",
    ]
    rows: list[dict[str, Any]] = []
    for block in report.get("content_gaps") or []:
        if not isinstance(block, dict):
            continue
        block_url = block.get("page_url")
        if page_url and block_url and _normalize_url(block_url) != _normalize_url(page_url):
            continue
        for gap in block.get("gaps") or []:
            if not isinstance(gap, dict):
                continue
            item = dict(gap)
            item.setdefault("best_page_url", block_url)
            if page_url:
                gap_page = item.get("best_page_url") or block_url
                if gap_page and _normalize_url(gap_page) != _normalize_url(page_url):
                    continue
            rows.append(item)
    if not rows:
        lines.append("_No content gaps listed for this page._")
        return "\n".join(lines)
    for gap in rows[:20]:
        gtype = escape_text(gap.get("gap_type") or "gap")
        sev = escape_text(gap.get("severity") or "—")
        rationale = escape_text(gap.get("rationale") or gap.get("explanation") or "")
        gid = escape_text(gap.get("gap_id") or "")
        lines.append(f"- **{gtype}** (severity: {sev}) {f'{gid} ' if gid else ''}— {rationale}")
    return "\n".join(lines)


def draft_ui_label(draft: dict[str, Any]) -> str:
    status = str(draft.get("status") or "")
    generator = str(draft.get("generator") or draft.get("writer") or "")
    if "hashnode_recommended" in generator.lower() or draft.get("content_provenance") == "recommended_from_source_markdown":
        return "RECOMMENDED MARKDOWN"
    if status == "skipped_paid_false" or not (draft.get("body_markdown") or "").strip():
        return "No draft generated"
    if "skeleton" in generator.lower():
        return "Optimization Draft (deterministic skeleton)"
    if status == "generated":
        return "Recommended Content (generated draft)"
    if status == "failed":
        return "Draft failed"
    return "Suggested Structure"


def adapt_draft(report: dict[str, Any], *, page_url: str | None = None) -> DraftView | None:
    drafts = [d for d in (report.get("content_drafts") or []) if isinstance(d, dict)]
    draft = None
    if page_url:
        for d in drafts:
            if _normalize_url(d.get("page_url")) == _normalize_url(page_url):
                draft = d
                break
    if draft is None and drafts:
        draft = drafts[0]
    if draft is None and isinstance(report.get("draft"), dict):
        draft = report["draft"]
    # Fall back to page_intelligence.recommended_markdown when drafts empty.
    if draft is None:
        pi = _page_intelligence_for(report, page_url)
        rec_md = pi.get("recommended_markdown") if isinstance(pi, dict) else None
        if isinstance(rec_md, str) and rec_md.strip():
            draft = {
                "page_url": page_url or pi.get("url"),
                "status": "generated",
                "generator": "hashnode_recommended_markdown_v1",
                "content_provenance": "recommended_from_source_markdown",
                "body_markdown": rec_md,
                "disclaimer": (
                    "RECOMMENDED MARKDOWN — suggested draft for Hashnode editor / "
                    "GitHub publish / bulk import. Not a final or guaranteed AEO article."
                ),
            }
    if draft is None:
        return None

    body = str(draft.get("body_markdown") or "")
    label = draft_ui_label(draft)
    empty = not body.strip()
    disclaimer = str(
        draft.get("disclaimer")
        or "Draft suggestion only — not published; not a guarantee of AI citation."
    )
    header = (
        f"### {escape_text(label)}\n\n"
        f"**Status:** {escape_text(draft.get('status'))} · "
        f"**Generator:** {escape_text(draft.get('generator') or draft.get('writer'))} · "
        f"**Provenance:** {escape_text(draft.get('content_provenance') or 'generated')}\n\n"
        f"_{escape_text(disclaimer)}_\n\n"
        "---\n\n"
    )
    if empty:
        md = header + (
            "_No meaningful recommended Markdown could be generated for this page "
            "without fabricating content._"
        )
    else:
        # Sanitize + fence; never inject raw HTML into Gradio Markdown unsafely.
        md = header + sanitize_code_block(body, language="markdown")

    return DraftView(
        page_url=str(draft.get("page_url") or page_url or ""),
        status=str(draft.get("status") or ""),
        generator=str(draft.get("generator") or draft.get("writer") or ""),
        content_provenance=str(draft.get("content_provenance") or "generated"),
        label=label,
        disclaimer=disclaimer,
        body_markdown=md,
        empty=empty,
    )


def adapt_recommended_markdown(
    report: dict[str, Any],
    *,
    page_url: str | None = None,
) -> str:
    """Primary RECOMMENDED MARKDOWN tab body — unfenced, copy-ready Markdown.

    Includes honesty labeling; raw draft body is not wrapped in fences so a
    Gradio Code/Textbox copy control can place the article on the clipboard.
    """
    draft = adapt_draft(report, page_url=page_url)
    raw = ""
    for d in report.get("content_drafts") or []:
        if not isinstance(d, dict):
            continue
        if page_url and _normalize_url(d.get("page_url")) != _normalize_url(page_url):
            continue
        raw = str(d.get("body_markdown") or "")
        break
    if not raw and isinstance(report.get("draft"), dict):
        raw = str(report["draft"].get("body_markdown") or "")
    if not raw:
        pi = _page_intelligence_for(report, page_url)
        raw = str((pi or {}).get("recommended_markdown") or "")

    if draft is None and not raw.strip():
        return (
            "# RECOMMENDED MARKDOWN\n\n"
            "No recommended Markdown draft for this page. "
            "When Hashnode Markdown is available, a complete suggested draft appears here — "
            "never labeled as a final or guaranteed AEO article.\n"
        )

    label = draft.label if draft else "RECOMMENDED MARKDOWN"
    disclaimer = (
        draft.disclaimer
        if draft
        else (
            "RECOMMENDED MARKDOWN — suggested draft for Hashnode editor / "
            "GitHub publish / bulk import. Not a final or guaranteed AEO article."
        )
    )
    status = draft.status if draft else "—"
    generator = draft.generator if draft else "—"
    provenance = draft.content_provenance if draft else "—"
    header = (
        f"# {label}\n\n"
        f"Status: {status} · Generator: {generator} · Provenance: {provenance}\n\n"
        f"_{disclaimer}_\n\n"
        "---\n\n"
    )
    if not raw.strip():
        return header + (
            "No meaningful recommended Markdown could be generated for this page "
            "without fabricating content.\n"
        )
    return header + raw.strip() + "\n"


def adapt_recommendations(report: dict[str, Any], *, page_url: str | None = None) -> list[RecView]:
    out: list[RecView] = []
    for rec in report.get("recommendations") or []:
        if not isinstance(rec, dict):
            continue
        urls = [str(u) for u in (rec.get("affected_urls") or [])]
        # Keep site-level recs (no URLs); filter page-scoped recs to selection.
        if page_url and urls:
            if _normalize_url(page_url) not in {_normalize_url(u) for u in urls}:
                continue
        snippets = [str(s) for s in (rec.get("evidence_snippets") or [])][:8]
        out.append(
            RecView(
                id=str(rec.get("id") or rec.get("code") or ""),
                title=str(rec.get("title") or rec.get("code") or ""),
                problem=str(rec.get("problem") or ""),
                why=str(rec.get("why_it_matters") or rec.get("rationale") or ""),
                action=str(rec.get("recommended_action") or ""),
                effort=str(rec.get("effort") or "—"),
                impact=rec.get("impact"),
                evidence_snippets=snippets,
                affected_urls=urls,
            )
        )
    return out


def recommendations_markdown(recs: list[RecView]) -> str:
    if not recs:
        return (
            "### WHY THESE CHANGES\n\n"
            "_No recommendation detail for this selection._\n\n"
            "_Site-level or other-page recommendations may still appear in Biggest Opportunities._"
        )
    parts: list[str] = [
        "### WHY THESE CHANGES",
        "",
        "_Audit / explanation of recommendation detail — secondary to the Markdown draft._",
        "",
    ]
    for i, r in enumerate(recs, start=1):
        parts.append(f"#### {i}. {escape_text(r.title)}")
        parts.append("")
        if r.problem:
            parts.append(f"**Problem:** {escape_text(r.problem)}")
        if r.why:
            parts.append(f"**Why it matters:** {escape_text(r.why)}")
        if r.action:
            parts.append(f"**Recommended action:** {escape_text(r.action)}")
        parts.append(f"**Effort:** {escape_text(r.effort)} · **Impact:** {escape_text(r.impact)}")
        if r.affected_urls:
            parts.append(
                "**Affected page:** " + ", ".join(escape_text(u) for u in r.affected_urls[:5])
            )
        if r.evidence_snippets:
            parts.append("")
            parts.append("Evidence:")
            parts.extend(f"- {escape_text(s)}" for s in r.evidence_snippets)
        parts.append("")
    return "\n".join(parts)


def _count_md_stats(text: str) -> tuple[int, int]:
    lines = (text or "").splitlines()
    headings = sum(1 for ln in lines if ln.lstrip().startswith("#"))
    sections = max(0, headings)
    return sections, headings


def comparison_markdown(
    report: dict[str, Any],
    page_url: str | None,
    *,
    pages_payload: dict[str, Any] | None = None,
) -> str:
    """Side-by-side CURRENT vs RECOMMENDED Markdown panes (HTML, not Git diff)."""
    return comparison_html(report, page_url, pages_payload=pages_payload)


def comparison_html(
    report: dict[str, Any],
    page_url: str | None,
    *,
    pages_payload: dict[str, Any] | None = None,
) -> str:
    """Diffchecker-like layout: two independent scroll panes (no Git unified diff)."""
    current = _source_markdown_for(report, page_url, pages_payload) or ""
    draft = adapt_draft(report, page_url=page_url)
    recommended = ""
    if draft and draft.body_markdown:
        # Prefer raw body from report drafts (without UI header chrome).
        for d in report.get("content_drafts") or []:
            if isinstance(d, dict) and (
                not page_url
                or _normalize_url(d.get("page_url")) == _normalize_url(page_url)
            ):
                recommended = str(d.get("body_markdown") or "")
                break
        if not recommended and isinstance(report.get("draft"), dict):
            recommended = str(report["draft"].get("body_markdown") or "")
        if not recommended:
            pi = _page_intelligence_for(report, page_url)
            recommended = str((pi or {}).get("recommended_markdown") or "")

    if not current and not recommended:
        before = adapt_before(report, page_url=page_url, pages_payload=pages_payload)
        # Non-Markdown pages: keep an honest signal summary (still no Git diff).
        left_text = (
            f"Title: {before.title or '—'}\n"
            f"URL: {before.page_url or '—'}\n"
            f"Word count: {before.word_count}\n\n"
            + "\n".join(f"# {h}" for h in before.headings[:12])
        )
        right_text = recommended or (
            draft.disclaimer if draft else "No recommended Markdown for this page."
        )
        current = left_text
        recommended = right_text if recommended else (
            "(No recommended Markdown draft — HTML page path uses brief/signals only.)"
        )

    cur_sec, cur_h = _count_md_stats(current)
    rec_sec, rec_h = _count_md_stats(recommended)
    summary = (
        f'<p class="aeo-compare-summary">'
        f"CURRENT: {cur_sec} sections / {cur_h} headings · "
        f"RECOMMENDED: {rec_sec} sections / {rec_h} headings"
        f"</p>"
    )

    return (
        '<div class="aeo-md-compare">'
        f"{summary}"
        '<div class="aeo-md-compare-grid">'
        '<div class="aeo-md-pane">'
        '<div class="aeo-md-pane-header">CURRENT MARKDOWN</div>'
        f'<pre class="aeo-md-scroll">{escape_text(current) or "—"}</pre>'
        "</div>"
        '<div class="aeo-md-pane">'
        '<div class="aeo-md-pane-header">RECOMMENDED MARKDOWN</div>'
        f'<pre class="aeo-md-scroll">{escape_text(recommended) or "—"}</pre>'
        "</div>"
        "</div>"
        '<p class="aeo-compare-note">'
        "Independent scroll panes — not a Git diff or patch view. "
        "Recommended draft is a suggestion, not a final/guaranteed AEO article."
        "</p>"
        "</div>"
    )


def loading_enrichment_markdown(section: str) -> str:
    return (
        f"### {section}\n\n"
        "_Additional optimization analysis loading…_\n\n"
        "_Observed page signals stay visible in CURRENT / Before while this loads._"
    )


def enrichment_error_markdown(section: str, message: str) -> str:
    return (
        f"### {section}\n\n"
        f"**Could not load additional analysis:** {escape_text(message)}\n\n"
        "_Page identity and observed signals above remain valid._"
    )


def adapt_evidence(report: dict[str, Any], *, page_url: str | None = None) -> EvidenceView:
    snippets: list[str] = []
    for rec in report.get("recommendations") or []:
        if not isinstance(rec, dict):
            continue
        urls = [str(u) for u in (rec.get("affected_urls") or [])]
        if page_url and urls and _normalize_url(page_url) not in {_normalize_url(u) for u in urls}:
            continue
        for s in rec.get("evidence_snippets") or []:
            snippets.append(str(s))
    snippets = snippets[:20]

    finding_lines: list[str] = []
    for pf in report.get("page_findings") or []:
        if not isinstance(pf, dict):
            continue
        if page_url and _normalize_url(pf.get("url")) != _normalize_url(page_url):
            continue
        title = pf.get("title") or pf.get("url") or "page"
        finding_lines.append(f"{title}: {pf.get('issue_count', 0)} issue(s)")
        for issue in (pf.get("issues") or [])[:5]:
            if isinstance(issue, dict):
                finding_lines.append(
                    f"  - {issue.get('code') or issue.get('id')}: {issue.get('summary') or issue.get('message') or ''}"
                )
            else:
                finding_lines.append(f"  - {issue}")

    provenance_notes: list[str] = []
    for brief in report.get("optimization_briefs") or []:
        if not isinstance(brief, dict):
            continue
        if page_url and _normalize_url(brief.get("page_url")) != _normalize_url(page_url):
            continue
        for n in brief.get("provenance_notes") or []:
            provenance_notes.append(str(n))

    caveats = [str(c) for c in (report.get("caveats") or [])][:10]
    lines = [
        "### Evidence",
        "",
        "_Factual observations driving content changes "
        "(gaps, headings, query alignment, visibility, terminology) — "
        "not a generic SEO checklist._",
        "",
    ]

    # Content gaps first — primary drivers for Markdown recommendations.
    gap_lines: list[str] = []
    for block in report.get("content_gaps") or []:
        if not isinstance(block, dict):
            continue
        block_url = block.get("page_url")
        if page_url and block_url and _normalize_url(block_url) != _normalize_url(page_url):
            continue
        for gap in block.get("gaps") or []:
            if not isinstance(gap, dict):
                continue
            gtype = escape_text(gap.get("gap_type") or "gap")
            rationale = escape_text(gap.get("rationale") or gap.get("explanation") or "")
            gap_lines.append(f"- **{gtype}** — {rationale}")
    if gap_lines:
        lines.append("#### Content gaps")
        lines.extend(gap_lines[:20])
        lines.append("")

    pi = _page_intelligence_for(report, page_url)
    if pi:
        headings = [str(h) for h in (pi.get("heading_outline") or [])][:12]
        if not headings:
            for h in pi.get("headings") or []:
                if isinstance(h, dict) and h.get("text"):
                    headings.append(str(h["text"]))
        if headings:
            lines.append("#### Heading outline")
            lines.extend(f"- {escape_text(h)}" for h in headings)
            lines.append("")
        wc = pi.get("word_count")
        if wc:
            lines.append(f"**Word count (derived):** {escape_text(wc)}")
            lines.append("")

    if snippets:
        lines.append("#### Evidence snippets")
        lines.extend(f"- {escape_text(s)}" for s in snippets)
        lines.append("")
    if finding_lines:
        lines.append("#### Page findings")
        lines.extend(f"- {escape_text(x)}" for x in finding_lines)
        lines.append("")
    if provenance_notes:
        lines.append("#### Provenance notes")
        lines.extend(f"- {escape_text(x)}" for x in provenance_notes)
        lines.append("")
    if caveats:
        lines.append("#### Report caveats")
        lines.extend(f"- {escape_text(c)}" for c in caveats)
    if len(lines) <= 5:
        lines.append("_No content evidence for this selection._")
        lines.append("")
        lines.append("_Try another page, or check Biggest Opportunities for site-level findings._")
    return EvidenceView(
        snippets=snippets,
        finding_lines=finding_lines,
        provenance_notes=provenance_notes,
        caveats=caveats,
        markdown="\n".join(lines),
    )


def overview_markdown(vm: OverviewVM) -> str:
    lines = [
        f"## Analysis overview",
        "",
        f"**Seed / base URL:** {escape_text(vm.base_url)}",
        f"**Mode:** {'Single page' if vm.mode == 'single' else 'Multi-page (same-host crawl from seed)'}",
        f"**Demo mode:** {'yes' if vm.demo_mode else 'no'}",
        f"**Pages crawled:** {vm.pages_crawled}"
        + (
            " _(demo fixtures load the full fixture site; API ignores max_pages/max_depth)_"
            if vm.demo_mode
            else ""
        ),
        f"**Job:** {escape_text(vm.job_id)}",
        "",
        f"### {escape_text(vm.health.label)}: **{escape_text(vm.health.value)}**",
        f"Provenance: {escape_text(vm.health.provenance)}",
        "",
        "### Component scores",
        "",
        "| Component | Score | Provenance |",
        "| --- | ---: | --- |",
    ]
    for c in vm.components:
        lines.append(f"| {escape_text(c.label)} | {escape_text(c.value)} | {escape_text(c.provenance)} |")
    if vm.visibility_lines:
        lines.append("")
        lines.append("### AI / LLM visibility ⓘ")
        lines.extend(f"- {line}" for line in vm.visibility_lines)
    if vm.executive_bullets:
        lines.append("")
        lines.append("### Executive summary")
        lines.extend(f"- {b}" for b in vm.executive_bullets)
    if vm.crawl_partial:
        lines.append("")
        lines.append(f"> **Partial crawl:** {vm.crawl_note}")
    if vm.caveats:
        lines.append("")
        lines.append("### Caveats")
        lines.extend(f"- {c}" for c in vm.caveats)
    return "\n".join(lines)


def merge_page_opt_into_report(report: dict[str, Any], opt: dict[str, Any]) -> dict[str, Any]:
    """Overlay per-page content-optimization response onto a shallow copy of report."""
    merged = dict(report)
    if opt.get("page_intelligence"):
        merged["page_intelligence"] = opt["page_intelligence"]
    if opt.get("content_gaps") is not None:
        merged["content_gaps"] = opt["content_gaps"]
    elif opt.get("gap_report"):
        merged["content_gaps"] = [opt["gap_report"]]
    if opt.get("optimization_briefs") is not None:
        merged["optimization_briefs"] = opt["optimization_briefs"]
    elif opt.get("brief"):
        merged["optimization_briefs"] = [opt["brief"]]
    if opt.get("content_drafts") is not None:
        merged["content_drafts"] = opt["content_drafts"]
    elif opt.get("draft"):
        merged["content_drafts"] = [opt["draft"]]
    return merged


@dataclass
class AnalysisState:
    """UI session state — cleared on new analysis / failed follow-up.

    ``enrichment_cache`` is session/job-scoped (lives on Gradio State), never
    a process-global cross-user cache.
    """

    job_id: str | None = None
    mode: str = "single"
    report: dict[str, Any] | None = None
    pages: dict[str, Any] | None = None
    selected_page_url: str | None = None
    error: str | None = None
    stage: str = ""
    opportunities: list[dict[str, Any]] = field(default_factory=list)
    selection_id: int = 0
    enrichment_cache: EnrichmentCache = field(default_factory=EnrichmentCache)
    last_options: dict[str, Any] = field(default_factory=dict)

    def clear_results(self) -> None:
        self.job_id = None
        self.report = None
        self.pages = None
        self.selected_page_url = None
        self.error = None
        self.stage = ""
        self.opportunities = []
        self.selection_id = next_selection_token(self.selection_id)
        self.enrichment_cache.clear()
        self.last_options = {}


def next_selection_token(current: int) -> int:
    from services.enrichment import next_selection_id

    return next_selection_id(current)
