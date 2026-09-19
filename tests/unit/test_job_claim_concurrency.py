"""P0-5: atomic single-job claim — one owner, zero loser side effects.

Deterministic barriers preferred over sleep races.
No live DigitalOcean / Hashnode calls.
"""

from __future__ import annotations

import asyncio
import json
import logging
import threading
from unittest.mock import patch

import pytest

from aeo_mvp.db.models import Job, VisibilityObservation, new_id, utc_now_iso
from aeo_mvp.db.session import get_session_factory, init_db, reset_engine
from aeo_mvp.pipeline.job_claim import (
    CLAIMED_STATUS,
    JobClaimConflict,
    claim_job,
    new_worker_id,
)
from aeo_mvp.pipeline.orchestrator import JobOrchestrator, create_job_record
from aeo_mvp.visibility.demo import DemoProvider
from aeo_mvp.visibility.digitalocean_web_search import DigitalOceanWebSearchError


def _pending_job(session, **options) -> Job:
    job = create_job_record(
        session,
        "https://demo.example/",
        demo_mode=True,
        options={"provider": "demo", "runs_per_prompt": 1, **options},
    )
    session.commit()
    return job


# --- A / B: single claim + second fails ---


def test_a_single_worker_claims_pending(db_session):
    job = _pending_job(db_session)
    claimed = claim_job(db_session, job.id, worker_id="w-a")
    assert claimed.status == CLAIMED_STATUS
    db_session.refresh(job)
    assert job.status == CLAIMED_STATUS


def test_b_second_claim_fails_atomically(db_session):
    job = _pending_job(db_session)
    claim_job(db_session, job.id, worker_id="w1")
    with pytest.raises(JobClaimConflict) as ei:
        claim_job(db_session, job.id, worker_id="w2")
    assert ei.value.reason == "already_running"
    assert ei.value.current_status == CLAIMED_STATUS


# --- C: concurrent claims → exactly one winner ---


def test_c_two_concurrent_claims_exactly_one_winner(tmp_path, monkeypatch):
    db_path = tmp_path / "claim_race.db"
    url = f"sqlite:///{db_path}"
    monkeypatch.setenv("AEO_DATABASE_URL", url)
    reset_engine()
    from aeo_mvp.config import get_settings

    get_settings.cache_clear()
    init_db(url)
    factory = get_session_factory(url)

    setup = factory()
    try:
        job = _pending_job(setup)
        job_id = job.id
    finally:
        setup.close()

    barrier = threading.Barrier(2)
    outcomes: list[str] = []
    lock = threading.Lock()

    def worker(wid: str) -> None:
        session = factory()
        try:
            barrier.wait(timeout=5)
            claim_job(session, job_id, worker_id=wid)
            with lock:
                outcomes.append("won")
        except JobClaimConflict:
            with lock:
                outcomes.append("lost")
        finally:
            session.close()

    t1 = threading.Thread(target=worker, args=("c1",))
    t2 = threading.Thread(target=worker, args=("c2",))
    t1.start()
    t2.start()
    t1.join(timeout=10)
    t2.join(timeout=10)
    assert sorted(outcomes) == ["lost", "won"]

    verify = factory()
    try:
        row = verify.get(Job, job_id)
        assert row is not None
        assert row.status == CLAIMED_STATUS
    finally:
        verify.close()
        reset_engine()
        get_settings.cache_clear()


# --- D / E / F: status guards ---


def test_d_claimed_running_cannot_be_started_by_another(db_session):
    job = _pending_job(db_session)
    claim_job(db_session, job.id, worker_id="owner")
    # Simulate mid-pipeline status owned by winner
    job.status = "crawling"
    job.updated_at = utc_now_iso()
    db_session.commit()

    with pytest.raises(JobClaimConflict) as ei:
        claim_job(db_session, job.id, worker_id="intruder")
    assert ei.value.reason == "already_running"
    assert ei.value.current_status == "crawling"


def test_e_completed_cannot_be_implicitly_reexecuted(db_session):
    job = _pending_job(db_session)
    job.status = "completed"
    job.completed_at = utc_now_iso()
    db_session.commit()

    with pytest.raises(JobClaimConflict) as ei:
        claim_job(db_session, job.id, worker_id="rerun")
    assert ei.value.reason == "completed"

    with pytest.raises(JobClaimConflict):
        asyncio.run(JobOrchestrator(db_session).run(job.id, worker_id="rerun"))
    db_session.refresh(job)
    assert job.status == "completed"


def test_f_failed_remains_claimable(db_session):
    """Preserve prior semantics: failed jobs can be re-invoked via run/claim."""
    job = _pending_job(db_session)
    job.status = "failed"
    job.error_message = "prior provider error"
    db_session.commit()

    claimed = claim_job(db_session, job.id, worker_id="retry")
    assert claimed.status == CLAIMED_STATUS
    assert claimed.error_message is None


# --- G: claim before expensive execution ---


@pytest.mark.asyncio
async def test_g_claim_before_expensive_execution(db_session):
    job = _pending_job(db_session)
    order: list[str] = []
    real_claim = claim_job

    def tracing_claim(session, job_id, **kwargs):
        order.append("claim")
        return real_claim(session, job_id, **kwargs)

    async def tracing_crawl(*args, **kwargs):
        order.append("crawl")
        # Status must already be claimed (committed) before crawl body.
        other = get_session_factory()()
        try:
            row = other.get(Job, job.id)
            assert row is not None
            # Same-session may have flushed crawling; durable commit is claimed+.
            assert row.status in (CLAIMED_STATUS, "crawling")
        finally:
            other.close()
        raise RuntimeError("stop-after-claim-check")

    with (
        patch("aeo_mvp.pipeline.orchestrator.claim_job", side_effect=tracing_claim),
        patch("aeo_mvp.pipeline.orchestrator.crawl_site", side_effect=tracing_crawl),
    ):
        with pytest.raises(RuntimeError, match="stop-after-claim-check"):
            await JobOrchestrator(db_session).run(job.id, worker_id="g")

    assert order[0] == "claim"
    assert "crawl" in order
    assert order.index("claim") < order.index("crawl")


# --- H / I: loser makes zero provider/crawl/observation side effects ---


@pytest.mark.asyncio
async def test_h_i_loser_zero_crawl_provider_observations(db_session):
    job = _pending_job(db_session)
    claim_job(db_session, job.id, worker_id="winner")

    crawl_calls: list = []
    provider_calls: list = []
    do_constructed: list = []
    opt_calls: list = []

    async def spy_crawl(*a, **k):
        crawl_calls.append(1)
        raise AssertionError("loser must not crawl")

    class SpyDemo(DemoProvider):
        async def run_query(self, query, *, context=None):  # type: ignore[no-untyped-def]
            provider_calls.append(query)
            raise AssertionError("loser must not call provider")

    class SpyDO:
        def __init__(self, *a, **k):
            do_constructed.append(1)
            raise AssertionError("loser must not construct DO")

    def spy_opt(*a, **k):
        opt_calls.append(1)
        raise AssertionError("loser must not run content optimization")

    with (
        patch("aeo_mvp.pipeline.orchestrator.crawl_site", side_effect=spy_crawl),
        patch("aeo_mvp.pipeline.orchestrator.DemoProvider", SpyDemo),
        patch(
            "aeo_mvp.pipeline.orchestrator.DigitalOceanWebSearchProvider", SpyDO
        ),
        patch("aeo_mvp.content.service.run_from_resolved", side_effect=spy_opt),
    ):
        with pytest.raises(JobClaimConflict) as ei:
            await JobOrchestrator(db_session).run(job.id, worker_id="loser")

    assert ei.value.reason == "already_running"
    assert crawl_calls == []
    assert provider_calls == []
    assert do_constructed == []
    assert opt_calls == []

    obs = (
        db_session.query(VisibilityObservation)
        .filter(VisibilityObservation.job_id == job.id)
        .count()
    )
    assert obs == 0
    db_session.refresh(job)
    assert job.status == CLAIMED_STATUS  # winner's claim unchanged; not failed


# --- J: winner completes full pipeline ---


@pytest.mark.asyncio
async def test_j_winner_completes_full_pipeline(db_session):
    job = _pending_job(db_session)
    result = await JobOrchestrator(db_session).run(job.id, worker_id="winner-j")
    db_session.commit()
    db_session.refresh(result)
    assert result.status == "completed"
    assert result.completed_at is not None
    obs = (
        db_session.query(VisibilityObservation)
        .filter(VisibilityObservation.job_id == job.id)
        .count()
    )
    assert obs > 0


# --- K: provider failure after claim → failed ---


@pytest.mark.asyncio
async def test_k_provider_failure_after_claim_marks_failed(db_session):
    job = _pending_job(db_session)

    async def boom_crawl(*a, **k):
        raise RuntimeError("provider-or-crawl boom")

    with patch("aeo_mvp.pipeline.orchestrator.crawl_site", side_effect=boom_crawl):
        with pytest.raises(RuntimeError, match="boom"):
            await JobOrchestrator(db_session).run(job.id, worker_id="k")

    db_session.refresh(job)
    assert job.status == "failed"
    assert job.error_message is not None
    assert "boom" in job.error_message


# --- L: lease not implemented — document via constant / conflict on stuck claim ---


def test_l_no_lease_stale_claimed_blocks_until_manual_reset(db_session):
    """Crash-after-claim: job stays claimed; reclaim requires reset to pending."""
    job = _pending_job(db_session)
    claim_job(db_session, job.id, worker_id="crashed")
    with pytest.raises(JobClaimConflict) as ei:
        claim_job(db_session, job.id, worker_id="recovery")
    assert ei.value.reason == "already_running"

    # Operator reset (no automatic lease reclaim)
    job.status = "pending"
    db_session.commit()
    reclaimed = claim_job(db_session, job.id, worker_id="recovery")
    assert reclaimed.status == CLAIMED_STATUS


# --- Observability: structured claim logs, no secrets ---


def test_claim_logs_success_and_conflict(db_session, caplog):
    job = _pending_job(db_session)
    with caplog.at_level(logging.INFO, logger="aeo_mvp.pipeline.job_claim"):
        claim_job(db_session, job.id, worker_id="log-w1")
        with pytest.raises(JobClaimConflict):
            claim_job(db_session, job.id, worker_id="log-w2")
    text = "\n".join(r.message for r in caplog.records)
    assert "job_claim_success" in text
    assert "job_claim_conflict" in text
    assert job.id in text
    assert "log-w1" in text
    assert "Authorization" not in text
    assert "Bearer" not in text


def test_new_worker_id_stable_shape():
    wid = new_worker_id()
    assert wid.startswith("pid-")
    assert len(wid) > 8


# --- M: API auth intact (claim path does not open unauthenticated jobs) ---


def test_m_api_auth_intact(client, api_key):
    naked = client.headers.pop("Authorization", None)
    try:
        r = client.post(
            "/api/v1/jobs",
            json={"url": "https://demo.example/", "demo_mode": True},
        )
        assert r.status_code == 401
    finally:
        if naked is not None:
            client.headers["Authorization"] = naked

    ok = client.post(
        "/api/v1/jobs",
        json={
            "url": "https://demo.example/",
            "demo_mode": True,
            "options": {"provider": "demo", "runs_per_prompt": 1},
        },
    )
    assert ok.status_code == 202
    assert ok.json()["status"] == "pending"


# --- N: DO paid gate intact ---


def test_n_do_paid_gate_intact(monkeypatch):
    from aeo_mvp.config import Settings, get_settings

    get_settings.cache_clear()
    isolated = Settings(
        _env_file=None,
        DO_MODEL_ACCESS_KEY="test-do-key-not-real",
        AEO_PAID_RETRIEVAL_OPT_IN=False,
    )
    monkeypatch.setattr(
        "aeo_mvp.pipeline.orchestrator.get_settings", lambda: isolated
    )
    orch = JobOrchestrator.__new__(JobOrchestrator)
    orch.settings = isolated

    class SpyDO:
        def __init__(self, *a, **k):
            raise AssertionError("DO must not construct when gate closed")

    job = Job(
        id=new_id(),
        base_url="https://demo.example/",
        demo_mode=0,
        status="pending",
        options_json=json.dumps({"provider": "digitalocean_web_search"}),
        created_at=utc_now_iso(),
        updated_at=utc_now_iso(),
    )
    with patch(
        "aeo_mvp.pipeline.orchestrator.DigitalOceanWebSearchProvider", SpyDO
    ):
        with pytest.raises(DigitalOceanWebSearchError, match="paid_retrieval_opt_in"):
            orch._select_provider(
                job,
                {"provider": "digitalocean_web_search"},
                allow_paid_retrieval=False,
            )
    get_settings.cache_clear()


# --- Claim conflict must not mark job failed via background runner ---


def test_background_claim_conflict_does_not_fail_job(tmp_path, monkeypatch):
    from aeo_mvp.api.routes import _run_pipeline
    from aeo_mvp.config import Settings, get_settings

    db_path = tmp_path / "bg.db"
    url = f"sqlite:///{db_path}"
    monkeypatch.setenv("AEO_DATABASE_URL", url)
    reset_engine()
    get_settings.cache_clear()
    isolated = Settings(_env_file=None, AEO_DATABASE_URL=url)
    monkeypatch.setattr("aeo_mvp.config.get_settings", lambda: isolated)
    init_db(url)
    factory = get_session_factory(url)

    s = factory()
    try:
        job = _pending_job(s)
        job_id = job.id
        claim_job(s, job_id, worker_id="owner")
    finally:
        s.close()

    _run_pipeline(job_id)

    s2 = factory()
    try:
        row = s2.get(Job, job_id)
        assert row is not None
        assert row.status == CLAIMED_STATUS
        assert row.error_message is None
    finally:
        s2.close()
        reset_engine()
        get_settings.cache_clear()
