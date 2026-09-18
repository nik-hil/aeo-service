"""Service helpers for content-optimization API (SSRF + job/page resolution)."""

from __future__ import annotations

import json
from typing import Any

import httpx
from sqlalchemy.orm import Session

from aeo_mvp.config import USER_AGENT, get_settings
from aeo_mvp.content.pipeline import run_content_optimization
from aeo_mvp.crawler.fetch import fetch_url
from aeo_mvp.db.models import ExperimentConfig, Job, Page, SiteProfile
from aeo_mvp.security.ssrf import SSRFError, assert_safe_public_url, is_obviously_unsafe_url


class OptimizationRequestError(ValueError):
    """Client-facing validation error for optimization requests."""


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
    assert_safe_public_url(url)
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
