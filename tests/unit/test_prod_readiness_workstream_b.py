"""Workstream B regressions: P1-10 URL persist/IP gate, P1-11 observation
idempotency under reclaim, P1-14 crawl failure honesty.

Preserves P0 claim/SSRF/auth/DO/OpenAI contracts. No live DO / Hashnode.
"""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from unittest.mock import patch

import pytest
from sqlalchemy.exc import IntegrityError

from aeo_mvp.crawler.discover import CrawlOutcome, crawl_demo
from aeo_mvp.db.models import (
    ExperimentConfig,
    Page,
    Report,
    VisibilityObservation,
    VisibilityObservation as VisObsRow,
    new_id,
    utc_now_iso,
)
from aeo_mvp.pipeline.orchestrator import (
    JobOrchestrator,
    clear_job_pipeline_artifacts,
    create_job_record,
)
from aeo_mvp.security.ssrf import SSRFError, is_obviously_unsafe_url, normalize_public_url
from aeo_mvp.visibility.base import VisibilityObservation as VisObsDTO
from aeo_mvp.visibility.openai_compatible import OpenAICompatibleError


# --- P1-10 ---


def test_p1_10_create_strips_userinfo_from_base_url(db_session, monkeypatch):
    from aeo_mvp.config import Settings, get_settings

    get_settings.cache_clear()
    settings = Settings(_env_file=None, AEO_DEMO_MODE=False)
    monkeypatch.setattr("aeo_mvp.config.get_settings", lambda: settings)
    monkeypatch.setattr(
        "aeo_mvp.pipeline.orchestrator.get_settings", lambda: settings
    )

    job = create_job_record(
        db_session,
        "https://user:p@ssw0rd@Example.COM/landing?x=1",
        demo_mode=False,
        options={},
    )
    db_session.commit()
    assert "user" not in job.base_url
    assert "p@ssw0rd" not in job.base_url
    assert "ssw0rd" not in job.base_url
    assert job.base_url == normalize_public_url(
        "https://user:p@ssw0rd@Example.COM/landing?x=1"
    )
    assert job.base_url.startswith("https://example.com/landing")
    assert job.demo_mode == 0


def test_p1_10_decimal_ip_rejected_at_create(db_session):
    assert is_obviously_unsafe_url("http://2130706433/") is True
    with pytest.raises(SSRFError):
        create_job_record(db_session, "http://2130706433/", demo_mode=False)


def test_p1_10_hex_ip_rejected_at_create(db_session):
    assert is_obviously_unsafe_url("http://0x7f000001/") is True
    with pytest.raises(SSRFError):
        create_job_record(db_session, "http://0x7f000001/", demo_mode=False)


def test_p1_10_create_gate_does_not_replace_fetch_ssrf():
    """Create-time check is cheap; public hostnames still pass without DNS."""
    assert is_obviously_unsafe_url("https://example.com/") is False
    assert is_obviously_unsafe_url("http://127.0.0.1/") is True


# --- P1-11 ---


def _vis_dto(prompt_id: str, run_index: int, query: str = "q") -> VisObsDTO:
    return VisObsDTO(
        provider_name="openai_compatible",
        engine_label="openai_compatible:test",
        query=query,
        prompt_id=prompt_id,
        run_index=run_index,
        observed_at=datetime.now(timezone.utc),
        raw_response="AcmeFlow is great.",
        raw_storage_permitted=True,
        detected_mention=True,
        detected_citation=False,
        cited_urls=[],
        extraction_methodology="test",
        provenance="api_observation",
        meta={"error": False},
        model_id="test",
        retrieval_enabled=False,
        experiment_kind="llm_mention",
    )


@pytest.mark.asyncio
async def test_p1_11_mid_provider_fail_leaves_no_partial_observations(
    db_session, monkeypatch
):
    from aeo_mvp.config import Settings, get_settings

    get_settings.cache_clear()
    settings = Settings(
        _env_file=None,
        OPENAI_API_KEY="sk-test-fake-not-real",
        AEO_DEMO_MODE=False,
    )
    monkeypatch.setattr("aeo_mvp.config.get_settings", lambda: settings)
    monkeypatch.setattr(
        "aeo_mvp.pipeline.orchestrator.get_settings", lambda: settings
    )

    calls = {"n": 0}

    async def boom_on_third(self, query, *, context):
        calls["n"] += 1
        if calls["n"] >= 3:
            raise OpenAICompatibleError(
                "upstream HTTP 500",
                category="upstream_http",
                status_code=500,
            )
        return _vis_dto(context.prompt_id, context.run_index, query)

    async def fake_crawl(session, job_id, base_url, **kwargs):
        return crawl_demo(session, job_id)

    job = create_job_record(
        db_session,
        "https://demo.example/",
        demo_mode=False,
        options={
            "provider": "openai_compatible",
            "runs_per_prompt": 1,
            "max_pages": 1,
            "content_optimization": False,
            # Force enough prompts via discovery fallback → fixed templates
        },
    )
    job.demo_mode = 0
    db_session.commit()

    with (
        patch("aeo_mvp.pipeline.orchestrator.crawl_site", side_effect=fake_crawl),
        patch(
            "aeo_mvp.visibility.openai_compatible.OpenAICompatibleProvider.run_query",
            boom_on_third,
        ),
    ):
        orch = JobOrchestrator(db_session)
        orch.settings = settings
        with pytest.raises(OpenAICompatibleError):
            await orch.run(job.id)

    db_session.refresh(job)
    assert job.status == "failed"
    rows = (
        db_session.query(VisObsRow).filter(VisObsRow.job_id == job.id).all()
    )
    assert rows == [], "partial observations must not commit on provider failure"


@pytest.mark.asyncio
async def test_p1_11_reclaim_does_not_duplicate_observations(db_session):
    job = create_job_record(
        db_session,
        "https://demo.example/",
        demo_mode=True,
        options={
            "provider": "demo",
            "runs_per_prompt": 1,
            "content_optimization": False,
        },
    )
    db_session.commit()

    await JobOrchestrator(db_session).run(job.id, worker_id="first")
    db_session.commit()
    db_session.refresh(job)
    assert job.status == "completed"
    first_count = (
        db_session.query(VisObsRow).filter(VisObsRow.job_id == job.id).count()
    )
    assert first_count > 0

    job.status = "failed"
    job.error_message = "sim reclaim"
    job.completed_at = None
    db_session.commit()

    await JobOrchestrator(db_session).run(job.id, worker_id="reclaim")
    db_session.commit()
    db_session.refresh(job)
    assert job.status == "completed"
    second_count = (
        db_session.query(VisObsRow).filter(VisObsRow.job_id == job.id).count()
    )
    assert second_count == first_count


def test_p1_11_unique_constraint_rejects_duplicate_obs(db_session):
    job = create_job_record(
        db_session,
        "https://demo.example/",
        demo_mode=True,
        options={"provider": "demo"},
    )
    db_session.flush()
    cfg = ExperimentConfig(
        id=new_id(),
        job_id=job.id,
        protocol_version="llm-mention-v1",
        provider_name="demo",
        model_id="demo",
        prompt_set_id="prompt-set-v1",
        prompts_json="[]",
        runs_per_prompt=1,
        created_at=utc_now_iso(),
    )
    db_session.add(cfg)
    db_session.flush()

    def _row():
        return VisObsRow(
            id=new_id(),
            job_id=job.id,
            experiment_config_id=cfg.id,
            provider_name="demo",
            engine_label="demo",
            query="q",
            prompt_id="p1",
            run_index=0,
            observed_at=utc_now_iso(),
            detected_mention=0,
            detected_citation=0,
            cited_urls_json="[]",
            extraction_methodology="t",
            provenance="synthetic_demo",
            meta_json="{}",
        )

    db_session.add(_row())
    db_session.flush()
    db_session.add(_row())
    with pytest.raises(IntegrityError):
        db_session.flush()
    db_session.rollback()


def test_p1_11_clear_artifacts_keeps_report(db_session):
    job = create_job_record(
        db_session,
        "https://demo.example/",
        demo_mode=True,
        options={"provider": "demo"},
    )
    db_session.flush()
    db_session.add(
        Page(
            id=new_id(),
            job_id=job.id,
            url="https://demo.example/",
            depth=0,
            status_code=200,
            html="<html></html>",
        )
    )
    db_session.add(
        Report(
            id=new_id(),
            job_id=job.id,
            report_json="{}",
            emitted_at=utc_now_iso(),
        )
    )
    db_session.commit()

    clear_job_pipeline_artifacts(db_session, job.id)
    db_session.commit()

    assert db_session.query(Page).filter_by(job_id=job.id).count() == 0
    assert db_session.query(Report).filter_by(job_id=job.id).count() == 1


# --- P1-14 ---


@pytest.mark.asyncio
async def test_p1_14_all_fetches_fail_is_crawl_failure_not_bad_seo(db_session):
    async def all_error_crawl(session, job_id, base_url, **kwargs):
        pages = []
        for i, url in enumerate(
            ["https://example.com/", "https://example.com/about"]
        ):
            p = Page(
                id=new_id(),
                job_id=job_id,
                url=url,
                final_url=url,
                depth=0 if i == 0 else 1,
                status_code=None,
                html=None,
                fetch_error="dns_failure",
                fetched_at=utc_now_iso(),
            )
            session.add(p)
            pages.append(p)
        session.flush()
        return CrawlOutcome(
            pages=pages,
            robots_raw=None,
            robots_allowed_root=0.5,
            crawl_status="failed",
            discovered=2,
            attempted=2,
            fetched=0,
            errors=2,
        )

    job = create_job_record(
        db_session,
        "https://example.com/",
        demo_mode=False,
        options={
            "provider": "demo",
            "content_optimization": False,
            "max_pages": 2,
        },
    )
    # Force non-demo so we use the patched crawl (create may still set demo via
    # provider=demo — override).
    job.demo_mode = 0
    db_session.commit()

    with patch(
        "aeo_mvp.pipeline.orchestrator.crawl_site", side_effect=all_error_crawl
    ):
        result = await JobOrchestrator(db_session).run(job.id, worker_id="crawl-fail")
    db_session.commit()
    db_session.refresh(result)

    assert result.status == "failed"
    assert result.status != "completed"
    assert result.error_message is not None
    assert "crawl_failed" in result.error_message
    assert "fetched=0" in result.error_message

    # Must not look like a completed weak-SEO success
    assert result.health_formula_version is None or result.status == "failed"

    report_row = db_session.query(Report).filter_by(job_id=job.id).one()
    report = json.loads(report_row.report_json)
    assert report["status"] == "failed"
    assert report["crawl"]["status"] == "failed"
    assert report["crawl"]["fetched"] == 0
    assert report["crawl"]["errors"] == 2
    assert report["crawl"]["attempted"] == 2
    assert any("crawl" in c.lower() and "failed" in c.lower() for c in report["caveats"])
    # Health absent / null — not a near-zero “bad SEO” score presented as success
    health = (report.get("scores") or {}).get("aeo_health") or {}
    assert health.get("value") is None


@pytest.mark.asyncio
async def test_p1_14_demo_crawl_status_ok(db_session):
    job = create_job_record(
        db_session,
        "https://demo.example/",
        demo_mode=True,
        options={"provider": "demo", "content_optimization": False, "runs_per_prompt": 1},
    )
    db_session.commit()
    await JobOrchestrator(db_session).run(job.id, worker_id="crawl-ok")
    db_session.commit()
    db_session.refresh(job)
    assert job.status == "completed"
    report = json.loads(db_session.query(Report).filter_by(job_id=job.id).one().report_json)
    assert report["crawl"]["status"] == "ok"
    assert report["crawl"]["fetched"] >= 1
    assert report["crawl"]["errors"] == 0


@pytest.mark.asyncio
async def test_p1_14_degraded_continues_with_caveat(db_session):
    async def mixed_crawl(session, job_id, base_url, **kwargs):
        ok_html = "<html><head><title>Home</title></head><body><h1>Hi</h1><p>Answer first content here for analyzers.</p></body></html>"
        pages = [
            Page(
                id=new_id(),
                job_id=job_id,
                url="https://example.com/",
                final_url="https://example.com/",
                depth=0,
                status_code=200,
                content_type="text/html",
                html=ok_html,
                title="Home",
                fetch_error=None,
                fetched_at=utc_now_iso(),
            ),
            Page(
                id=new_id(),
                job_id=job_id,
                url="https://example.com/broken",
                final_url="https://example.com/broken",
                depth=1,
                status_code=None,
                html=None,
                fetch_error="timeout",
                fetched_at=utc_now_iso(),
            ),
        ]
        for p in pages:
            session.add(p)
        session.flush()
        return CrawlOutcome(
            pages=pages,
            robots_raw=None,
            robots_allowed_root=0.5,
            crawl_status="degraded",
            discovered=2,
            attempted=2,
            fetched=1,
            errors=1,
        )

    job = create_job_record(
        db_session,
        "https://example.com/",
        demo_mode=False,
        options={
            "provider": "demo",
            "content_optimization": False,
            "runs_per_prompt": 1,
            "discovery_only": True,
        },
    )
    job.demo_mode = 0
    db_session.commit()

    with patch(
        "aeo_mvp.pipeline.orchestrator.crawl_site", side_effect=mixed_crawl
    ):
        result = await JobOrchestrator(db_session).run(job.id, worker_id="degraded")
    db_session.commit()
    db_session.refresh(result)
    assert result.status == "completed"
    report = json.loads(
        db_session.query(Report).filter_by(job_id=job.id).one().report_json
    )
    assert report["crawl"]["status"] == "degraded"
    assert report["crawl"]["fetched"] == 1
    assert report["crawl"]["errors"] == 1
    assert any("degraded" in c.lower() for c in report["caveats"])
