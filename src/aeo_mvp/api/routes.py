"""HTTP routes for AEO MVP."""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request
from sqlalchemy.orm import Session

from aeo_mvp.api.schemas import (
    ContentOptimizationRequest,
    ContentOptimizationResponse,
    CreateJobRequest,
    HealthResponse,
    JobCreatedResponse,
    JobLinks,
    JobOptions,
    JobStatusResponse,
    PageItem,
    PagesResponse,
)
from aeo_mvp.config import get_settings
from aeo_mvp.db.models import Job, Page, Report, ScoreComponent
from aeo_mvp.db.session import get_session_factory
from aeo_mvp.content.service import (
    OptimizationRequestError,
    fetch_html_ssrf_safe,
    load_site_profile,
    prepare_queryset,
    resolve_page_html,
    run_from_resolved,
)
from aeo_mvp.pipeline.job_claim import JobClaimConflict
from aeo_mvp.pipeline.orchestrator import JobOrchestrator, create_job_record
from aeo_mvp.security.ssrf import SSRFError, is_obviously_unsafe_url

logger = logging.getLogger(__name__)

router = APIRouter()
api_router = APIRouter(prefix="/api/v1")


def _run_pipeline(job_id: str) -> None:
    """Background runner — sync wrapper around async orchestrator."""
    factory = get_session_factory()
    session = factory()
    try:
        asyncio.run(JobOrchestrator(session).run(job_id))
        session.commit()
    except JobClaimConflict as exc:
        # Claim conflict ≠ provider failure; do not flip job to failed.
        session.rollback()
        logger.info(
            "background pipeline claim conflict job_id=%s reason=%s "
            "current_status=%s",
            job_id,
            exc.reason,
            exc.current_status,
        )
    except Exception:  # noqa: BLE001
        session.rollback()
        logger.exception("background pipeline failed for %s", job_id)
    finally:
        session.close()


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(status="ok")


@api_router.post("/jobs", response_model=JobCreatedResponse, status_code=202)
def create_job(
    body: CreateJobRequest,
    background_tasks: BackgroundTasks,
) -> JobCreatedResponse:
    # Persist JobOptions defaults (incl. content_optimization=True) so stored
    # options_json matches API schema defaults and orchestrator execution.
    options = (body.options or JobOptions()).model_dump(exclude_none=True)
    # ADR-026 fail-closed: env AEO_PAID_RETRIEVAL_OPT_IN is the master switch.
    # Schema default false must not mask env true; request true cannot bypass
    # env false.
    settings = get_settings()
    req_paid = bool(options.get("paid_retrieval_opt_in", False))
    env_paid = bool(settings.paid_retrieval_opt_in)
    if req_paid and not env_paid:
        logger.info(
            "create_job: request paid_retrieval_opt_in=true ignored; "
            "AEO_PAID_RETRIEVAL_OPT_IN=false (ADR-026 fail-closed)"
        )
    options["paid_retrieval_opt_in"] = env_paid
    if not body.demo_mode and is_obviously_unsafe_url(body.url):
        raise HTTPException(
            status_code=400,
            detail=f"Unsafe URL rejected by SSRF policy: {body.url!r}",
        )
    factory = get_session_factory()
    session = factory()
    try:
        job = create_job_record(
            session,
            body.url,
            demo_mode=body.demo_mode,
            options=options,
        )
        session.commit()
        job_id = job.id
        created_at = job.created_at
        base_url = job.base_url
        demo_mode = bool(job.demo_mode)
    except Exception as exc:  # noqa: BLE001
        session.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    finally:
        session.close()

    background_tasks.add_task(_run_pipeline, job_id)
    return JobCreatedResponse(
        id=job_id,
        base_url=base_url,
        status="pending",
        demo_mode=demo_mode,
        created_at=created_at,
        links=JobLinks(
            self=f"/api/v1/jobs/{job_id}",
            report=f"/api/v1/jobs/{job_id}/report",
            pages=f"/api/v1/jobs/{job_id}/pages",
        ),
    )


def _job_or_404(session: Session, job_id: str) -> Job:
    job = session.get(Job, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"Unknown job {job_id}")
    return job


@api_router.get("/jobs/{job_id}", response_model=JobStatusResponse)
def get_job(job_id: str) -> JobStatusResponse:
    factory = get_session_factory()
    session = factory()
    try:
        job = _job_or_404(session, job_id)
        scores = (
            session.query(ScoreComponent)
            .filter(ScoreComponent.job_id == job.id)
            .all()
        )
        by = {s.component: s.score for s in scores}
        health_score = by.get("health")
        component_scores = None
        if any(k in by for k in ("technical", "content", "entity", "structured_data", "answerability")):
            component_scores = {
                k: by[k]
                for k in ("technical", "content", "entity", "structured_data", "answerability")
                if k in by
            }
        return JobStatusResponse(
            id=job.id,
            base_url=job.base_url,
            status=job.status,
            demo_mode=bool(job.demo_mode),
            error_message=job.error_message,
            health_score=round(health_score, 1) if health_score is not None else None,
            health_formula_version=job.health_formula_version,
            experiment_protocol_version=job.experiment_protocol_version,
            component_scores=component_scores,
            created_at=job.created_at,
            updated_at=job.updated_at,
            completed_at=job.completed_at,
        )
    finally:
        session.close()


@api_router.get("/jobs/{job_id}/report")
def get_report(job_id: str) -> dict[str, Any]:
    factory = get_session_factory()
    session = factory()
    try:
        job = _job_or_404(session, job_id)
        if job.status not in ("completed", "failed"):
            raise HTTPException(
                status_code=409,
                detail=f"Report not ready; job status is '{job.status}'",
            )
        if job.status == "failed":
            raise HTTPException(
                status_code=409,
                detail=f"Job failed: {job.error_message or 'unknown error'}",
            )
        report = session.query(Report).filter(Report.job_id == job.id).one_or_none()
        if report is None:
            raise HTTPException(status_code=404, detail="Report not found")
        return json.loads(report.report_json)
    finally:
        session.close()


@api_router.get("/jobs/{job_id}/pages", response_model=PagesResponse)
def get_pages(job_id: str) -> PagesResponse:
    factory = get_session_factory()
    session = factory()
    try:
        _job_or_404(session, job_id)
        pages = session.query(Page).filter(Page.job_id == job_id).order_by(Page.depth, Page.url).all()
        return PagesResponse(
            job_id=job_id,
            count=len(pages),
            pages=[
                PageItem(
                    id=p.id,
                    url=p.url,
                    final_url=p.final_url,
                    source_url=getattr(p, "source_url", None),
                    content_representation=getattr(p, "content_representation", None),
                    canonical_url=getattr(p, "canonical_url", None),
                    depth=p.depth,
                    status_code=p.status_code,
                    primary_status_code=getattr(p, "primary_status_code", None),
                    primary_fetch_status=getattr(p, "primary_fetch_status", None),
                    alternate_fetch_status=getattr(p, "alternate_fetch_status", None),
                    title=p.title,
                    fetch_error=p.fetch_error,
                    source_markdown=getattr(p, "source_markdown", None),
                )
                for p in pages
            ],
        )
    finally:
        session.close()


@api_router.post(
    "/content-optimization",
    response_model=ContentOptimizationResponse,
    status_code=200,
)
async def content_optimization(body: ContentOptimizationRequest) -> dict[str, Any]:
    """Grounded page optimization: intelligence → gaps → brief → draft.

    Accepts SSRF-safe ``source_url``, or existing ``job_id``/``page_id`` (+ queryset),
    or offline ``html``. Rejects free-form topic generation payloads (extra fields forbidden).
    Paid LLM default OFF; never auto-runs DigitalOcean web_search.
    Empty/missing HTML → 400/409 unless ``allow_empty_html`` (P1-8).
    """
    factory = get_session_factory()
    session = factory()
    try:
        try:
            html, url, title_hint, page_extras = resolve_page_html(
                session,
                job_id=body.job_id,
                page_id=body.page_id,
                source_url=body.source_url,
                html=body.html,
                url_hint=body.url,
                allow_empty_html=bool(body.allow_empty_html),
            )
        except OptimizationRequestError as exc:
            detail = str(exc)
            # Align with jobs routes: unknown job/page → 404.
            # Job page present but empty/missing HTML → 409 conflict.
            if detail.startswith("Unknown job") or " not found on job " in detail:
                status = 404
            elif body.job_id and "empty or missing HTML" in detail:
                status = 409
            else:
                status = 400
            raise HTTPException(status_code=status, detail=detail) from exc
        except SSRFError as exc:
            raise HTTPException(
                status_code=400,
                detail=f"Unsafe URL rejected by SSRF policy: {exc}",
            ) from exc

        if body.source_url and html is None:
            try:
                html, url, title_hint = await fetch_html_ssrf_safe(body.source_url)
            except SSRFError as exc:
                raise HTTPException(
                    status_code=400,
                    detail=f"Unsafe URL rejected by SSRF policy: {exc}",
                ) from exc
            except OptimizationRequestError as exc:
                raise HTTPException(status_code=502, detail=str(exc)) from exc

        job = session.get(Job, body.job_id) if body.job_id else None
        queryset = prepare_queryset(session, job, body.queryset)
        site_profile = body.site_profile
        if site_profile is None and job is not None:
            site_profile = load_site_profile(session, job)

        settings = get_settings()
        draft_paid = bool(body.draft_paid or body.paid_llm_opt_in)
        content_draft = bool(body.content_draft or body.generate_draft)
        generate_draft = content_draft
        api_key = settings.openai_api_key if draft_paid else None
        cfg = dict(body.config or {})
        cfg["generate_draft"] = generate_draft
        cfg["content_draft"] = content_draft
        cfg["content_draft_provider"] = body.content_draft_provider
        cfg["draft_paid"] = draft_paid

        try:
            from aeo_mvp.content.service import _attach_hashnode_recommended_markdown

            wire = run_from_resolved(
                html=html,
                url=url,
                title_hint=title_hint,
                queryset=queryset,
                site_profile=site_profile,
                config=cfg,
                generate_draft=generate_draft,
                draft_paid=draft_paid,
                llm_api_key=api_key,
                allow_empty_html=bool(body.allow_empty_html),
            )
            return _attach_hashnode_recommended_markdown(
                wire,
                page_url=url,
                page_id=page_extras.get("page_id"),
                title=title_hint,
                source_markdown=page_extras.get("source_markdown"),
                content_representation=page_extras.get("content_representation"),
                source_url=page_extras.get("source_url"),
                canonical_url=page_extras.get("canonical_url"),
                draft_paid=draft_paid,
                llm_api_key=api_key,
                llm_model=cfg.get("llm_model"),
                llm_base_url=cfg.get("llm_base_url"),
            )
        except OptimizationRequestError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
    finally:
        session.close()
