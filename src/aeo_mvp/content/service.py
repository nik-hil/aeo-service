"""Service helpers for content-optimization API (SSRF + job/page resolution)."""

from __future__ import annotations

import json
from typing import Any

import httpx
from sqlalchemy.orm import Session

from aeo_mvp.config import USER_AGENT, get_settings
from aeo_mvp.content.models import CONTENT_OPTIMIZATION_METHODOLOGY
from aeo_mvp.content.pipeline import run_content_optimization
from aeo_mvp.crawler.fetch import fetch_url
from aeo_mvp.db.models import ExperimentConfig, Job, Page, SiteProfile
from aeo_mvp.security.ssrf import SSRFError, is_obviously_unsafe_url


class OptimizationRequestError(ValueError):
    """Client-facing validation error for optimization requests."""


def _page_has_html(page: Page) -> bool:
    return bool(page.html and str(page.html).strip())


def optimize_job_pages(
    pages: list[Page],
    *,
    queryset: Any,
    site_profile: dict[str, Any] | None,
    options: dict[str, Any] | None = None,
    visibility_observations: list[dict[str, Any]] | None = None,
    llm_api_key: str | None = None,
) -> dict[str, Any]:
    """Run Phase 5 for crawled job pages via shared ``run_content_optimization``.

    Returns a report-ready section. Honest skip semantics when no pages / no HTML.
    Never enables paid DO retrieval. Draft stays Null unless content_draft/draft_paid.
    """
    opts = dict(options or {})
    content_draft = bool(opts.get("content_draft") or opts.get("generate_draft"))
    draft_paid = bool(opts.get("draft_paid") or opts.get("paid_llm_opt_in"))
    cfg = {
        "generate_draft": content_draft,
        "content_draft": content_draft,
        "content_draft_provider": opts.get("content_draft_provider"),
        "draft_paid": draft_paid,
    }
    # Fail-safe: only pass LLM key when paid draft is explicitly opted in.
    api_key = llm_api_key if draft_paid else None

    base: dict[str, Any] = {
        "methodology": CONTENT_OPTIMIZATION_METHODOLOGY,
        "enabled": True,
        "paid_retrieval": False,
        "paid_llm": False,
        "pages_considered": len(pages),
        "pages_optimized": 0,
        "page_ids": [],
        "skipped_page_ids": [],
    }

    if not pages:
        return {
            **base,
            "status": "skipped_no_pages",
            "page_intelligence": None,
            "content_gaps": [],
            "optimization_briefs": [],
            "content_drafts": [],
            "warnings": ["no_crawled_pages"],
        }

    eligible = [p for p in pages if _page_has_html(p)]
    skipped = [p.id for p in pages if not _page_has_html(p)]
    base["skipped_page_ids"] = skipped

    if not eligible:
        return {
            **base,
            "status": "skipped_no_html",
            "page_intelligence": None,
            "content_gaps": [],
            "optimization_briefs": [],
            "content_drafts": [],
            "warnings": ["no_eligible_page_html"],
        }

    # Stable order: depth then URL (same as resolve_page_html primary pick).
    eligible_sorted = sorted(
        eligible, key=lambda p: (int(p.depth or 0), p.url or "", p.id or "")
    )

    content_gaps: list[dict[str, Any]] = []
    optimization_briefs: list[dict[str, Any]] = []
    content_drafts: list[dict[str, Any]] = []
    page_ids: list[str] = []
    primary_intel: dict[str, Any] | None = None
    any_paid_llm = False

    for page in eligible_sorted:
        result = run_content_optimization(
            html=page.html,
            url=page.url or "",
            title_hint=page.title,
            queryset=queryset,
            site_profile=site_profile,
            config=cfg,
            generate_draft=content_draft,
            draft_paid=draft_paid,
            llm_api_key=api_key,
            visibility_observations=visibility_observations,
        )
        wire = result.to_dict()
        intel = dict(wire["page_intelligence"])
        intel["page_id"] = page.id
        if primary_intel is None:
            primary_intel = intel
        # One gap-report / brief / draft per optimized page (list shape matches standalone).
        for gap_doc in wire.get("content_gaps") or []:
            g = dict(gap_doc)
            g.setdefault("page_url", page.url or "")
            g.setdefault("page_id", page.id)
            content_gaps.append(g)
        for brief_doc in wire.get("optimization_briefs") or []:
            b = dict(brief_doc)
            b.setdefault("page_url", page.url or "")
            b.setdefault("target_url", page.url or b.get("target_url"))
            optimization_briefs.append(b)
        for draft_doc in wire.get("content_drafts") or []:
            d = dict(draft_doc)
            d.setdefault("page_url", page.url or "")
            content_drafts.append(d)
        page_ids.append(page.id)
        any_paid_llm = any_paid_llm or bool(wire.get("paid_llm"))

    return {
        **base,
        "status": "completed",
        "pages_optimized": len(page_ids),
        "page_ids": page_ids,
        "page_intelligence": primary_intel,
        "content_gaps": content_gaps,
        "optimization_briefs": optimization_briefs,
        "content_drafts": content_drafts,
        "paid_llm": any_paid_llm,
        # Compat singular aliases (primary page) — same as standalone wire
        "gap_report": content_gaps[0] if content_gaps else None,
        "brief": optimization_briefs[0] if optimization_briefs else None,
        "draft": content_drafts[0] if content_drafts else None,
    }


def _load_queryset_from_job(session: Session, job: Job) -> dict[str, Any] | None:
    cfg = (
        session.query(ExperimentConfig)
        .filter(ExperimentConfig.job_id == job.id)
        .order_by(ExperimentConfig.created_at.desc())
        .first()
    )
    if not cfg or not cfg.discovered_queries_json:
        return None
    try:
        data = json.loads(cfg.discovered_queries_json)
    except json.JSONDecodeError:
        return None
    if isinstance(data, dict):
        return data
    if isinstance(data, list):
        return {"members": [{"query": q} for q in data], "query_set_version": "query-set-v3"}
    return None


def load_site_profile(session: Session, job: Job) -> dict[str, Any] | None:
    row = session.query(SiteProfile).filter(SiteProfile.job_id == job.id).one_or_none()
    if not row or not row.profile_json:
        return None
    try:
        return json.loads(row.profile_json)
    except json.JSONDecodeError:
        return None


def resolve_page_html(
    session: Session,
    *,
    job_id: str | None,
    page_id: str | None,
    source_url: str | None,
    html: str | None,
    url_hint: str | None,
) -> tuple[str | None, str, str | None]:
    if html is not None and source_url:
        raise OptimizationRequestError(
            "Provide either html (offline) or source_url (live), not both"
        )

    if job_id:
        job = session.get(Job, job_id)
        if job is None:
            raise OptimizationRequestError(f"Unknown job {job_id}")
        page: Page | None = None
        if page_id:
            page = session.get(Page, page_id)
            if page is None or page.job_id != job.id:
                raise OptimizationRequestError(
                    f"Page {page_id} not found on job {job_id}"
                )
        else:
            pages = (
                session.query(Page)
                .filter(Page.job_id == job.id)
                .order_by(Page.depth, Page.url)
                .all()
            )
            page = pages[0] if pages else None
        if page is None:
            raise OptimizationRequestError(f"Job {job_id} has no pages")
        return page.html, page.url, page.title

    if source_url:
        if is_obviously_unsafe_url(source_url):
            raise SSRFError(f"Unsafe URL rejected by SSRF policy: {source_url!r}")
        return None, source_url, None

    if html is not None:
        return html, url_hint or "", None

    raise OptimizationRequestError(
        "Provide job_id (+ optional page_id), or source_url, or html (+ optional url)"
    )


async def fetch_html_ssrf_safe(url: str) -> tuple[str | None, str, str | None]:
    settings = get_settings()
    # SSRF resolve+validate+IP-pin happens once inside fetch_url (no prior resolve).
    async with httpx.AsyncClient(headers={"User-Agent": USER_AGENT}) as client:
        result = await fetch_url(client, url, timeout_s=settings.crawl_timeout_s)
    if result.error or not result.text:
        raise OptimizationRequestError(
            f"Failed to fetch source_url: {result.error or 'empty_body'}"
        )
    return result.text, result.final_url or url, None


def run_from_resolved(
    *,
    html: str | None,
    url: str,
    title_hint: str | None,
    queryset: Any,
    site_profile: dict[str, Any] | None,
    config: dict[str, Any] | None,
    generate_draft: bool,
    draft_paid: bool,
    llm_api_key: str | None,
) -> dict[str, Any]:
    result = run_content_optimization(
        html=html,
        url=url,
        title_hint=title_hint,
        queryset=queryset,
        site_profile=site_profile,
        config=config,
        generate_draft=generate_draft,
        draft_paid=draft_paid,
        llm_api_key=llm_api_key,
    )
    return result.to_dict()


def prepare_queryset(
    session: Session,
    job: Job | None,
    queryset: dict[str, Any] | list[Any] | None,
) -> Any:
    if queryset is not None:
        return queryset
    if job is not None:
        return _load_queryset_from_job(session, job)
    return {"members": [], "query_set_version": "query-set-v3"}
