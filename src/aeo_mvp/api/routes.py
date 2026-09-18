"""HTTP routes for AEO MVP."""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request
from sqlalchemy.orm import Session

from aeo_mvp.api.schemas import (
    CreateJobRequest,
    HealthResponse,
    JobCreatedResponse,
    JobLinks,
    JobStatusResponse,
    PageItem,
    PagesResponse,
)
from aeo_mvp.db.models import Job, Page, Report, ScoreComponent
from aeo_mvp.db.session import get_session_factory
from aeo_mvp.pipeline.orchestrator import JobOrchestrator, create_job_record

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
    options = body.options.model_dump() if body.options else {}
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
                    depth=p.depth,
                    status_code=p.status_code,
                    title=p.title,
                    fetch_error=p.fetch_error,
                )
                for p in pages
            ],
        )
    finally:
        session.close()
