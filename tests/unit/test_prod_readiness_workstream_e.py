"""Workstream E — low-risk P2 / doc-aligned consistency.

- Content-opt unknown job/page → 404 (same as /jobs)
- Empty-page taxonomy assert tightened in phase5 suite (not here)
- Dead maybe_digitalocean_provider removed

No live DO / Hashnode. No CI / lease / trusted-base-URL systems.
"""

from __future__ import annotations

import aeo_mvp.visibility.digitalocean_web_search as do_mod
from aeo_mvp.db.models import Page, new_id
from aeo_mvp.db.session import get_session_factory
from aeo_mvp.pipeline.orchestrator import create_job_record


def test_e_content_opt_unknown_job_404(client):
    r = client.post(
        "/api/v1/content-optimization",
        json={"job_id": "does-not-exist-job", "generate_draft": False},
    )
    assert r.status_code == 404
    assert "Unknown job" in r.json()["detail"]


def test_e_content_opt_unknown_page_404(client):
    session = get_session_factory()()
    try:
        job = create_job_record(
            session,
            "https://demo.example/",
            demo_mode=True,
            options={},
        )
        session.commit()
        job_id = job.id
    finally:
        session.close()

    r = client.post(
        "/api/v1/content-optimization",
        json={
            "job_id": job_id,
            "page_id": "missing-page-id",
            "generate_draft": False,
        },
    )
    assert r.status_code == 404
    assert "not found on job" in r.json()["detail"]


def test_e_jobs_unknown_still_404(client):
    r = client.get("/api/v1/jobs/does-not-exist-job")
    assert r.status_code == 404


def test_e_maybe_digitalocean_provider_removed():
    assert not hasattr(do_mod, "maybe_digitalocean_provider")


def test_e_empty_html_still_409_not_404(client):
    """Empty page on a known job remains 409 (P1-8), not remapped to 404."""
    session = get_session_factory()()
    try:
        job = create_job_record(
            session,
            "https://empty.example/",
            demo_mode=False,
            options={},
        )
        page = Page(
            id=new_id(),
            job_id=job.id,
            url="https://empty.example/",
            final_url="https://empty.example/",
            depth=0,
            status_code=200,
            title=None,
            html=None,
            fetch_error=None,
        )
        session.add(page)
        session.commit()
        job_id, page_id = job.id, page.id
    finally:
        session.close()

    r = client.post(
        "/api/v1/content-optimization",
        json={"job_id": job_id, "page_id": page_id, "generate_draft": False},
    )
    assert r.status_code == 409
    assert "empty or missing HTML" in r.json()["detail"]
