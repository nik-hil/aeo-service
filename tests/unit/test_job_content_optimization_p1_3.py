"""P1-3: wire JobOptions.content_optimization into the job pipeline (Phase 5).

Proves execution via mocks/spies; no external network or paid providers.
"""

from __future__ import annotations

import asyncio
import json
from unittest.mock import patch

import pytest

from aeo_mvp.api.schemas import JobOptions
from aeo_mvp.content.models import (
    BRIEF_VERSION,
    CONTENT_OPTIMIZATION_METHODOLOGY,
    DRAFT_VERSION,
    GAP_VERSION,
    PAGE_INTEL_VERSION,
)
from aeo_mvp.content.pipeline import run_content_optimization
from aeo_mvp.content.service import optimize_job_pages
from aeo_mvp.db.models import Job, Page, Report, new_id, utc_now_iso
from aeo_mvp.pipeline.orchestrator import JobOrchestrator, create_job_record
from aeo_mvp.report.builder import build_report


def _run_demo(session, **opts):
    job = create_job_record(
        session,
        "https://demo.example/",
        demo_mode=True,
        options={"provider": "demo", "runs_per_prompt": 1, **opts},
    )
    session.commit()
    asyncio.run(JobOrchestrator(session).run(job.id))
    session.commit()
    session.refresh(job)
    return job


def _report(session, job: Job) -> dict:
    row = session.query(Report).filter_by(job_id=job.id).one()
    return json.loads(row.report_json)


# --- A: true → Phase 5 path executes ---


def test_a_content_optimization_true_executes_phase5(db_session):
    calls: list[dict] = []
    real = run_content_optimization

    def spy(**kwargs):
        calls.append(kwargs)
        return real(**kwargs)

    with patch(
        "aeo_mvp.content.service.run_content_optimization",
        side_effect=spy,
    ):
        job = _run_demo(db_session, content_optimization=True)

    assert job.status == "completed"
    assert calls, "Phase 5 run_content_optimization must execute when true"
    assert all(kw.get("html") for kw in calls)
    report = _report(db_session, job)
    assert report["content_optimization"]["status"] == "completed"
    assert report["content_optimization"]["enabled"] is True
    assert report["content_optimization"]["pages_optimized"] >= 1


# --- B: false → does NOT execute ---


def test_b_content_optimization_false_does_not_execute(db_session):
    calls: list = []

    def spy(**kwargs):
        calls.append(kwargs)
        raise AssertionError("Phase 5 must not run when content_optimization=false")

    with patch(
        "aeo_mvp.content.service.run_content_optimization",
        side_effect=spy,
    ):
        job = _run_demo(db_session, content_optimization=False)

    assert job.status == "completed"
    assert calls == []
    report = _report(db_session, job)
    assert report["content_optimization"]["enabled"] is False
    assert report["content_optimization"]["status"] == "disabled"
    assert report["content_optimization"]["pages_optimized"] == 0


# --- C: API default + stored option match execution ---


def test_c_api_default_and_stored_option_match_execution(client):
    opts = JobOptions()
    assert opts.content_optimization is True

    r = client.post(
        "/api/v1/jobs",
        json={
            "url": "https://demo.example/",
            "demo_mode": True,
            "options": {"provider": "demo", "runs_per_prompt": 1},
        },
    )
    assert r.status_code == 202
    job_id = r.json()["id"]

    # TestClient runs BackgroundTasks inline before response returns for sync routes,
    # but job may still be in flight; poll status.
    import time

    status = None
    for _ in range(80):
        jr = client.get(f"/api/v1/jobs/{job_id}")
        status = jr.json()["status"]
        if status in ("completed", "failed"):
            break
        time.sleep(0.05)
    assert status == "completed"

    from aeo_mvp.db.session import get_session_factory

    session = get_session_factory()()
    try:
        job = session.get(Job, job_id)
        stored = json.loads(job.options_json or "{}")
        assert stored.get("content_optimization") is True
        report_row = session.query(Report).filter_by(job_id=job_id).one()
        report = json.loads(report_row.report_json)
        assert report["content_optimization"]["enabled"] is True
        assert report["content_optimization"]["status"] == "completed"
        assert "page_intelligence" in report
    finally:
        session.close()


def test_c2_omitted_options_persist_schema_default(client):
    r = client.post(
        "/api/v1/jobs",
        json={"url": "https://demo.example/", "demo_mode": True},
    )
    assert r.status_code == 202
    job_id = r.json()["id"]
    from aeo_mvp.db.session import get_session_factory

    session = get_session_factory()()
    try:
        job = session.get(Job, job_id)
        stored = json.loads(job.options_json or "{}")
        assert stored.get("content_optimization") is True
        assert stored.get("content_draft") is False
        assert stored.get("draft_paid") is False
    finally:
        session.close()


# --- D: completed job with true has expected Phase 5 report fields ---


def test_d_completed_job_report_has_phase5_fields(db_session):
    job = _run_demo(db_session, content_optimization=True)
    report = _report(db_session, job)

    assert "page_intelligence" in report
    assert report["page_intelligence"]["page_intel_version"] == PAGE_INTEL_VERSION
    assert isinstance(report["content_gaps"], list) and report["content_gaps"]
    assert report["content_gaps"][0]["gap_report_version"] == GAP_VERSION
    assert isinstance(report["optimization_briefs"], list) and report["optimization_briefs"]
    assert report["optimization_briefs"][0]["brief_version"] == BRIEF_VERSION
    assert isinstance(report["content_drafts"], list) and report["content_drafts"]
    assert report["content_drafts"][0]["draft_version"] == DRAFT_VERSION
    assert (
        report["methodology"]["content_optimization_methodology"]
        == CONTENT_OPTIMIZATION_METHODOLOGY
    )
    assert report["content_optimization"]["methodology"] == CONTENT_OPTIMIZATION_METHODOLOGY
    assert report["paid_retrieval"] is False


# --- E: false does not falsely claim optimization ---


def test_e_false_does_not_claim_optimization(db_session):
    job = _run_demo(db_session, content_optimization=False)
    report = _report(db_session, job)

    assert "page_intelligence" not in report
    assert "content_gaps" not in report
    assert "optimization_briefs" not in report
    assert "content_drafts" not in report
    assert report["content_optimization"]["status"] == "disabled"
    assert report["content_optimization"]["pages_optimized"] == 0


# --- F: standalone /content-optimization unchanged ---


def test_f_standalone_content_optimization_unchanged(client):
    r = client.post(
        "/api/v1/content-optimization",
        json={
            "html": (
                "<html><head><title>Acme Docs</title></head>"
                "<body><h1>Acme</h1><p>How to configure Acme for AEO.</p></body></html>"
            ),
            "url": "https://acme.example/docs",
            "queryset": {
                "query_set_version": "query-set-v3",
                "members": [
                    {
                        "query_id": "q1",
                        "query": "How to configure Acme?",
                        "intent": "informational",
                    }
                ],
            },
            "generate_draft": False,
            "draft_paid": False,
        },
    )
    assert r.status_code == 200
    data = r.json()
    assert data["page_intelligence"]["page_intel_version"] == PAGE_INTEL_VERSION
    assert data["content_gaps"]
    assert data["optimization_briefs"]
    assert data["content_drafts"]
    assert data["content_drafts"][0]["status"] == "skipped_paid_false"
    assert data["paid_retrieval"] is False
    assert data["paid_llm"] is False


# --- G: null/default draft unchanged ---


def test_g_default_draft_is_null_skipped(db_session):
    job = _run_demo(db_session, content_optimization=True)
    report = _report(db_session, job)
    drafts = report["content_drafts"]
    assert drafts
    for d in drafts:
        assert d["status"] == "skipped_paid_false"
        assert d["generator"] in ("null",)
        assert d["paid"] is False
        assert d["paid_llm"] is False
        assert d["content_provenance"] == "generated"


# --- H: paid draft opt-in only ---


def test_h_paid_draft_opt_in_only(db_session):
    # Without draft_paid: Null generator path — no paid LLM
    job = _run_demo(
        db_session,
        content_optimization=True,
        content_draft=False,
        draft_paid=False,
    )
    report = _report(db_session, job)
    assert report["paid_llm"] is False
    assert all(d["paid_llm"] is False for d in report["content_drafts"])

    # With content_draft but not draft_paid → skeleton, still unpaid
    job2 = _run_demo(
        db_session,
        content_optimization=True,
        content_draft=True,
        draft_paid=False,
    )
    report2 = _report(db_session, job2)
    assert report2["paid_llm"] is False
    assert all(d["paid"] is False for d in report2["content_drafts"])
    assert all(
        d["status"] in ("generated", "skipped_paid_false", "failed")
        for d in report2["content_drafts"]
    )
    assert all(d["generator"] != "openai_compatible" for d in report2["content_drafts"])


# --- I: no DO paid retrieval side effect ---


def test_i_no_do_paid_retrieval_side_effect(db_session, monkeypatch):
    from aeo_mvp.config import Settings, get_settings
    from aeo_mvp.visibility.digitalocean_web_search import DigitalOceanWebSearchProvider

    get_settings.cache_clear()
    isolated = Settings(
        _env_file=None,
        DO_MODEL_ACCESS_KEY="test-do-key-not-real",
        AEO_PAID_RETRIEVAL_OPT_IN=False,
        AEO_DEMO_MODE=False,
    )
    monkeypatch.setattr(
        "aeo_mvp.pipeline.orchestrator.get_settings",
        lambda: isolated,
    )

    constructed: list = []

    class SpyDO(DigitalOceanWebSearchProvider):
        def __init__(self, *a, **k):
            constructed.append(True)
            raise AssertionError("DO must not be constructed during content optimization")

    with patch(
        "aeo_mvp.pipeline.orchestrator.DigitalOceanWebSearchProvider",
        SpyDO,
    ):
        job = _run_demo(
            db_session,
            content_optimization=True,
            paid_retrieval_opt_in=False,
            provider="demo",
        )

    assert job.status == "completed"
    assert constructed == []
    report = _report(db_session, job)
    assert report["content_optimization"]["paid_retrieval"] is False
    assert report.get("paid_retrieval") is False


# --- J: provenance observed ≠ derived ≠ generated ---


def test_j_provenance_observed_derived_generated(db_session):
    job = _run_demo(db_session, content_optimization=True, content_draft=True)
    report = _report(db_session, job)

    intel = report["page_intelligence"]
    for block in intel.get("answer_blocks") or []:
        assert block.get("provenance") in ("observed", "compatibility", "derived")
        assert block.get("provenance") != "generated"

    for gap_report in report["content_gaps"]:
        for gap in gap_report.get("gaps") or []:
            # gap wire may omit provenance; evidence provenance when present
            for ev in gap.get("evidence") or []:
                if "provenance" in ev:
                    assert ev["provenance"] in (
                        "observed",
                        "derived",
                        "compatibility",
                        "estimate",
                        "synthetic_demo",
                    )
                    assert ev["provenance"] != "generated"

    for draft in report["content_drafts"]:
        assert draft["content_provenance"] == "generated"
        assert draft["content_provenance"] != "observed"
        assert draft["content_provenance"] != "derived"


# --- K: does not run before page data available ---


def test_k_does_not_run_before_page_data(db_session):
    """Phase 5 must be invoked only after crawl pages exist (html present)."""
    order: list[str] = []
    real_opt = optimize_job_pages

    def spy_optimize(pages, **kwargs):
        order.append("phase5")
        assert pages, "Phase 5 must not run with empty page list when crawl succeeded"
        assert any(p.html for p in pages)
        return real_opt(pages, **kwargs)

    from aeo_mvp.crawler.discover import crawl_site as real_crawl

    async def spy_crawl(*a, **k):
        order.append("crawl")
        result = await real_crawl(*a, **k)
        assert result.pages
        return result

    with (
        patch("aeo_mvp.pipeline.orchestrator.crawl_site", side_effect=spy_crawl),
        patch(
            "aeo_mvp.pipeline.orchestrator.optimize_job_pages",
            side_effect=spy_optimize,
        ),
    ):
        job = _run_demo(db_session, content_optimization=True)

    assert job.status == "completed"
    assert order.index("crawl") < order.index("phase5")


def test_k2_no_html_honest_skip_semantics():
    """Missing HTML must not manufacture a successful optimization."""
    page = Page(
        id=new_id(),
        job_id=new_id(),
        url="https://empty.example/",
        depth=0,
        html=None,
        title=None,
        status_code=200,
        fetched_at=utc_now_iso(),
    )
    section = optimize_job_pages(
        [page],
        queryset={"members": [], "query_set_version": "query-set-v3"},
        site_profile=None,
        options={"content_optimization": True},
    )
    assert section["status"] == "skipped_no_html"
    assert section["pages_optimized"] == 0
    assert section["page_intelligence"] is None
    assert section["content_gaps"] == []
    assert section["optimization_briefs"] == []
    assert section["content_drafts"] == []
    assert "no_eligible_page_html" in section["warnings"]


def test_k3_no_pages_honest_skip():
    section = optimize_job_pages(
        [],
        queryset={"members": [], "query_set_version": "query-set-v3"},
        site_profile=None,
    )
    assert section["status"] == "skipped_no_pages"
    assert section["pages_optimized"] == 0
    assert section["page_intelligence"] is None


# --- L: helper shares pipeline; report disabled shape ---


def test_l_optimize_job_pages_shares_run_content_optimization():
    page = Page(
        id=new_id(),
        job_id=new_id(),
        url="https://acme.example/",
        depth=0,
        html="<html><head><title>Acme</title></head><body><h1>Acme</h1><p>Product docs.</p></body></html>",
        title="Acme",
        status_code=200,
        fetched_at=utc_now_iso(),
    )
    calls: list = []
    real = run_content_optimization

    def spy(**kwargs):
        calls.append(1)
        return real(**kwargs)

    with patch(
        "aeo_mvp.content.service.run_content_optimization",
        side_effect=spy,
    ):
        section = optimize_job_pages(
            [page],
            queryset={
                "query_set_version": "query-set-v3",
                "members": [
                    {
                        "query_id": "q1",
                        "query": "What is Acme?",
                        "intent": "informational",
                    }
                ],
            },
            site_profile={"organization_brand": "Acme"},
            options={"content_draft": False, "draft_paid": False},
        )
    assert calls == [1]
    assert section["status"] == "completed"
    assert section["page_intelligence"]["page_intel_version"] == PAGE_INTEL_VERSION
    assert section["content_drafts"][0]["status"] == "skipped_paid_false"


def test_report_builder_disabled_section_additive(db_session):
    job = create_job_record(
        db_session,
        "https://demo.example/",
        demo_mode=True,
        options={"provider": "demo", "content_optimization": False},
    )
    db_session.commit()
    asyncio.run(JobOrchestrator(db_session).run(job.id))
    db_session.commit()
    # Force rebuild from stash
    db_session.refresh(job)
    report = build_report(db_session, job)
    assert report["content_optimization"]["status"] == "disabled"
    assert "page_intelligence" not in report
