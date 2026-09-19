"""P0-1 / ADR-026: paid DigitalOcean retrieval requires explicit opt-in ∧ ready QuerySet.

Proves ZERO DO HTTP / provider invocation when the gate is closed — not log-only checks.
A configured DO API key must never implicitly authorize paid retrieval.
"""

from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from aeo_mvp.config import Settings, get_settings
from aeo_mvp.crawler.discover import crawl_demo
from aeo_mvp.db.models import ExperimentConfig, Job, new_id, utc_now_iso
from aeo_mvp.pipeline.orchestrator import JobOrchestrator, create_job_record
from aeo_mvp.queries.discovery import DiscoveryResult, DiscoveredQuery
from aeo_mvp.visibility.demo import DemoProvider
from aeo_mvp.visibility.digitalocean_web_search import (
    DigitalOceanWebSearchError,
    DigitalOceanWebSearchProvider,
)


def _job(options: dict | None = None, *, demo_mode: bool = False) -> Job:
    return Job(
        id=new_id(),
        base_url="https://demo.example/",
        demo_mode=1 if demo_mode else 0,
        status="pending",
        options_json=json.dumps(options or {}, sort_keys=True),
        created_at=utc_now_iso(),
        updated_at=utc_now_iso(),
    )


def _settings_with_do_key(monkeypatch, *, key: str | None = "test-do-key-not-real"):
    """Settings with DO key from constructor (not .env leak)."""
    monkeypatch.delenv("DO_MODEL_ACCESS_KEY", raising=False)
    monkeypatch.delenv("MODEL_ACCESS_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("AEO_PAID_RETRIEVAL_OPT_IN", raising=False)
    get_settings.cache_clear()
    kwargs: dict = {"_env_file": None, "AEO_PAID_RETRIEVAL_OPT_IN": False}
    if key is not None:
        kwargs["DO_MODEL_ACCESS_KEY"] = key
    isolated = Settings(**kwargs)
    monkeypatch.setattr(
        "aeo_mvp.pipeline.orchestrator.get_settings",
        lambda: isolated,
    )
    return isolated


def test_allow_paid_do_retrieval_requires_both_flags():
    assert (
        JobOrchestrator._allow_paid_do_retrieval(
            paid_opt_in=True, paid_retrieval_ready=True
        )
        is True
    )
    assert (
        JobOrchestrator._allow_paid_do_retrieval(
            paid_opt_in=False, paid_retrieval_ready=True
        )
        is False
    )
    assert (
        JobOrchestrator._allow_paid_do_retrieval(
            paid_opt_in=True, paid_retrieval_ready=False
        )
        is False
    )
    assert (
        JobOrchestrator._allow_paid_do_retrieval(
            paid_opt_in=False, paid_retrieval_ready=False
        )
        is False
    )


def test_select_provider_auto_with_do_key_but_no_opt_in_skips_do(monkeypatch):
    """Bug repro: key present + auto must NOT construct DO when gate closed."""
    settings = _settings_with_do_key(monkeypatch)
    orch = JobOrchestrator.__new__(JobOrchestrator)
    orch.settings = settings
    constructed: list = []

    class SpyDO(DigitalOceanWebSearchProvider):
        def __init__(self, *a, **k):
            constructed.append("constructed")
            raise AssertionError("DigitalOceanWebSearchProvider must not be constructed")

    with patch(
        "aeo_mvp.pipeline.orchestrator.DigitalOceanWebSearchProvider", SpyDO
    ):
        provider, model_id, fallback = orch._select_provider(
            _job({"provider": "auto", "paid_retrieval_opt_in": False}),
            {"provider": "auto", "paid_retrieval_opt_in": False},
            allow_paid_retrieval=False,
        )
    assert constructed == []
    assert isinstance(provider, DemoProvider)
    assert fallback is True
    assert model_id is None


def test_select_provider_auto_allows_do_when_gate_open(monkeypatch):
    settings = _settings_with_do_key(monkeypatch)
    orch = JobOrchestrator.__new__(JobOrchestrator)
    orch.settings = settings
    constructed: list = []

    class SpyDO:
        name = "digitalocean_web_search"
        model = "openai-gpt-4o"

        def __init__(self, *a, **k):
            constructed.append(True)

    with patch(
        "aeo_mvp.pipeline.orchestrator.DigitalOceanWebSearchProvider", SpyDO
    ):
        provider, model_id, fallback = orch._select_provider(
            _job({"provider": "auto"}),
            {"provider": "auto"},
            allow_paid_retrieval=True,
        )
    assert constructed == [True]
    assert provider.name == "digitalocean_web_search"
    assert model_id == "openai-gpt-4o"
    assert fallback is False


def test_select_provider_explicit_do_without_gate_raises(monkeypatch):
    settings = _settings_with_do_key(monkeypatch)
    orch = JobOrchestrator.__new__(JobOrchestrator)
    orch.settings = settings
    with pytest.raises(DigitalOceanWebSearchError, match="paid_retrieval_opt_in"):
        orch._select_provider(
            _job({"provider": "digitalocean_web_search"}),
            {"provider": "digitalocean_web_search"},
            allow_paid_retrieval=False,
        )


def test_select_provider_explicit_do_opt_in_but_no_key_raises(monkeypatch):
    settings = _settings_with_do_key(monkeypatch, key=None)
    orch = JobOrchestrator.__new__(JobOrchestrator)
    orch.settings = settings
    with pytest.raises(DigitalOceanWebSearchError, match="DO_MODEL_ACCESS_KEY"):
        orch._select_provider(
            _job({"provider": "digitalocean_web_search"}),
            {"provider": "digitalocean_web_search"},
            allow_paid_retrieval=True,
        )


def test_dotenv_do_key_does_not_bypass_opt_in_gate(monkeypatch, tmp_path):
    """A key in .env must not authorize DO when allow_paid_retrieval is false."""
    env_file = tmp_path / ".env"
    env_file.write_text("DO_MODEL_ACCESS_KEY=secret-from-dotenv\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("DO_MODEL_ACCESS_KEY", raising=False)
    monkeypatch.delenv("MODEL_ACCESS_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    get_settings.cache_clear()

    leaky = Settings()  # loads .env
    assert leaky.effective_do_api_key == "secret-from-dotenv"
    monkeypatch.setattr(
        "aeo_mvp.pipeline.orchestrator.get_settings",
        lambda: leaky,
    )

    orch = JobOrchestrator.__new__(JobOrchestrator)
    orch.settings = leaky
    constructed: list = []

    class SpyDO:
        def __init__(self, *a, **k):
            constructed.append(True)
            raise AssertionError("DO must not be constructed without opt-in")

    with patch(
        "aeo_mvp.pipeline.orchestrator.DigitalOceanWebSearchProvider", SpyDO
    ):
        provider, _, fallback = orch._select_provider(
            _job({"provider": "auto"}),
            {"provider": "auto", "paid_retrieval_opt_in": False},
            allow_paid_retrieval=False,
        )
    assert constructed == []
    assert isinstance(provider, DemoProvider)
    assert fallback is True
    get_settings.cache_clear()


async def _fake_crawl(session, job_id, base_url, **kwargs):
    return crawl_demo(session, job_id)


def _http_spy():
    """Return (mock_client_factory, post_calls) tracking DO httpx posts."""
    post_calls: list = []
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "id": "resp_test",
        "output": [
            {
                "type": "web_search_call",
                "status": "completed",
                "id": "ws_1",
                "action": {"type": "search", "queries": ["q"], "sources": []},
            },
            {
                "type": "message",
                "content": [{"type": "output_text", "text": "ok", "annotations": []}],
            },
        ],
    }
    mock_resp.text = "{}"

    mock_client = AsyncMock()
    mock_client.__aenter__.return_value = mock_client
    mock_client.__aexit__.return_value = None

    async def _post(*a, **k):
        post_calls.append((a, k))
        return mock_resp

    mock_client.post = AsyncMock(side_effect=_post)
    return mock_client, post_calls


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "discovery_only,paid_opt_in,do_key,expect_do_http",
    [
        (True, False, "present", False),
        (False, False, "present", False),
        (False, True, None, False),  # no key → no DO HTTP
        (False, True, "present", True),  # ready queryset from demo crawl
        (True, True, "present", False),  # discovery_only forces skip
        (False, False, None, False),
    ],
    ids=[
        "discovery_only+no_opt_in+key",
        "full_job+no_opt_in+key",
        "opt_in+no_key",
        "opt_in+key+ready",
        "discovery_only+opt_in+key",
        "no_opt_in+no_key",
    ],
)
async def test_orchestrator_do_http_behavior_matrix(
    db_session,
    monkeypatch,
    discovery_only,
    paid_opt_in,
    do_key,
    expect_do_http,
):
    key = "test-do-key-not-real" if do_key == "present" else None
    settings = _settings_with_do_key(monkeypatch, key=key)
    # Orchestrator caches settings on __init__
    monkeypatch.setattr(
        "aeo_mvp.pipeline.orchestrator.get_settings",
        lambda: settings,
    )

    options = {
        "provider": "auto",
        "paid_retrieval_opt_in": paid_opt_in,
        "discovery_only": discovery_only,
        "runs_per_prompt": 1,
        "query_top_n": 20,
    }
    job = create_job_record(
        db_session,
        "https://demo.example/",
        demo_mode=False,
        options=options,
    )
    # create_job_record may force demo if settings.demo_mode; ensure non-demo
    job.demo_mode = 0
    db_session.commit()

    mock_client, post_calls = _http_spy()
    constructed: list = []
    run_query_calls: list = []

    real_do = DigitalOceanWebSearchProvider

    class SpyDO(real_do):
        def __init__(self, *a, **k):
            constructed.append(True)
            super().__init__(api_key=key or "unused")

        async def run_query(self, query, *, context):
            run_query_calls.append(query)
            return await super().run_query(query, context=context)

    with (
        patch(
            "aeo_mvp.pipeline.orchestrator.crawl_site",
            side_effect=_fake_crawl,
        ),
        patch(
            "aeo_mvp.pipeline.orchestrator.DigitalOceanWebSearchProvider",
            SpyDO,
        ),
        patch(
            "aeo_mvp.visibility.digitalocean_web_search.httpx.AsyncClient",
            return_value=mock_client,
        ),
    ):
        orch = JobOrchestrator(db_session)
        orch.settings = settings
        if expect_do_http:
            await orch.run(job.id)
        elif paid_opt_in and do_key is None and not discovery_only:
            # auto falls through to Demo when no OpenAI and no allowed DO
            await orch.run(job.id)
        else:
            await orch.run(job.id)

    db_session.refresh(job)
    assert job.status == "completed"

    if expect_do_http:
        assert constructed, "DO provider should be constructed when gate open"
        assert run_query_calls, "DO run_query should execute when gate open"
        assert post_calls, "DO HTTP should occur when gate open"
        cfg = (
            db_session.query(ExperimentConfig)
            .filter_by(job_id=job.id)
            .one()
        )
        assert cfg.provider_name == "digitalocean_web_search"
        assert cfg.retrieval_enabled == 1
    else:
        assert constructed == [], "DO provider must not be constructed"
        assert run_query_calls == [], "DO run_query must not be called"
        assert post_calls == [], "ZERO DigitalOcean HTTP required"
        cfg = (
            db_session.query(ExperimentConfig)
            .filter_by(job_id=job.id)
            .one()
        )
        if discovery_only:
            assert cfg.provider_name == "discovery_only"
            assert cfg.retrieval_enabled == 0
            assert cfg.runs_per_prompt == 0
        else:
            assert cfg.provider_name != "digitalocean_web_search"
            assert cfg.retrieval_enabled == 0


@pytest.mark.asyncio
async def test_opt_in_true_but_queryset_not_ready_zero_do_http(db_session, monkeypatch):
    settings = _settings_with_do_key(monkeypatch, key="test-do-key-not-real")
    options = {
        "provider": "auto",
        "paid_retrieval_opt_in": True,
        "discovery_only": False,
        "runs_per_prompt": 1,
    }
    job = create_job_record(
        db_session, "https://demo.example/", demo_mode=False, options=options
    )
    job.demo_mode = 0
    db_session.commit()

    mock_client, post_calls = _http_spy()
    constructed: list = []

    class SpyDO:
        name = "digitalocean_web_search"
        model = "openai-gpt-4o"

        def __init__(self, *a, **k):
            constructed.append(True)
            raise AssertionError("DO must not construct when QuerySet not ready")

    def _not_ready_discovery(*a, **k):
        return DiscoveryResult(
            queries=[
                DiscoveredQuery(
                    id="q1",
                    query="What is AcmeFlow?",
                    classification="brand",
                    intent="brand",
                    score=0.9,
                )
            ],
            candidates_count=1,
            selected_count=1,
            paid_retrieval_opt_in=True,
            paid_retrieval_ready=False,  # ADR-026: not ready
            fallback_used=False,
        )

    with (
        patch(
            "aeo_mvp.pipeline.orchestrator.crawl_site",
            side_effect=_fake_crawl,
        ),
        patch(
            "aeo_mvp.pipeline.orchestrator.discover_queries",
            side_effect=_not_ready_discovery,
        ),
        patch(
            "aeo_mvp.pipeline.orchestrator.DigitalOceanWebSearchProvider",
            SpyDO,
        ),
        patch(
            "aeo_mvp.visibility.digitalocean_web_search.httpx.AsyncClient",
            return_value=mock_client,
        ),
    ):
        orch = JobOrchestrator(db_session)
        orch.settings = settings
        await orch.run(job.id)

    db_session.refresh(job)
    assert job.status == "completed"
    assert constructed == []
    assert post_calls == []
    cfg = db_session.query(ExperimentConfig).filter_by(job_id=job.id).one()
    assert cfg.provider_name != "digitalocean_web_search"
    assert cfg.retrieval_enabled == 0


@pytest.mark.asyncio
async def test_explicit_do_provider_without_opt_in_fails_before_http(
    db_session, monkeypatch
):
    settings = _settings_with_do_key(monkeypatch, key="test-do-key-not-real")
    options = {
        "provider": "digitalocean_web_search",
        "paid_retrieval_opt_in": False,
        "runs_per_prompt": 1,
    }
    job = create_job_record(
        db_session, "https://demo.example/", demo_mode=False, options=options
    )
    job.demo_mode = 0
    db_session.commit()

    mock_client, post_calls = _http_spy()
    constructed: list = []

    class SpyDO:
        def __init__(self, *a, **k):
            constructed.append(True)
            raise AssertionError("must not construct")

    with (
        patch(
            "aeo_mvp.pipeline.orchestrator.crawl_site",
            side_effect=_fake_crawl,
        ),
        patch(
            "aeo_mvp.pipeline.orchestrator.DigitalOceanWebSearchProvider",
            SpyDO,
        ),
        patch(
            "aeo_mvp.visibility.digitalocean_web_search.httpx.AsyncClient",
            return_value=mock_client,
        ),
    ):
        orch = JobOrchestrator(db_session)
        orch.settings = settings
        with pytest.raises(DigitalOceanWebSearchError, match="paid_retrieval_opt_in"):
            await orch.run(job.id)

    assert constructed == []
    assert post_calls == []
    db_session.refresh(job)
    assert job.status == "failed"
