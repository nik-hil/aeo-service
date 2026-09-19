"""P0-4: OpenAI provider failures must fail closed — never SUCCESS with zero mentions.

Deterministic unit tests. Isolated config. No network. No real .env secrets.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from aeo_mvp.config import Settings, get_settings
from aeo_mvp.crawler.discover import crawl_demo
from aeo_mvp.db.models import Job, VisibilityObservation as VisObsRow
from aeo_mvp.pipeline.orchestrator import JobOrchestrator, create_job_record
from aeo_mvp.visibility.base import VisibilityContext, VisibilityObservation
from aeo_mvp.visibility.demo import DemoProvider
from aeo_mvp.visibility.openai_compatible import (
    OpenAICompatibleError,
    OpenAICompatibleProvider,
    redact_secrets,
)


async def _fake_crawl(session, job_id, base_url, **kwargs):
    return crawl_demo(session, job_id)


FAKE_KEY = "sk-test-fake-key-not-real-ABCDEFGH"
FAKE_BEARER = f"Bearer {FAKE_KEY}"


def _ctx(**kwargs) -> VisibilityContext:
    base = dict(
        job_id="job-test-1",
        base_url="https://acme.example/",
        brand_tokens=["AcmeFlow"],
        site_registrable_domain="acme.example",
        prompt_id="ps1_brand",
        run_index=0,
    )
    base.update(kwargs)
    return VisibilityContext(**base)


def _ok_completion(content: str) -> dict:
    return {
        "id": "chatcmpl-test",
        "choices": [{"message": {"role": "assistant", "content": content}}],
        "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
    }


def _mock_client(resp: MagicMock) -> AsyncMock:
    mock_client = AsyncMock()
    mock_client.__aenter__.return_value = mock_client
    mock_client.__aexit__.return_value = None
    mock_client.post = AsyncMock(return_value=resp)
    return mock_client


def _http_resp(
    *,
    status_code: int = 200,
    json_data: dict | None = None,
    text: str = "",
    json_raises: Exception | None = None,
) -> MagicMock:
    mock_resp = MagicMock()
    mock_resp.status_code = status_code
    mock_resp.text = text
    if json_raises is not None:
        mock_resp.json.side_effect = json_raises
    else:
        mock_resp.json.return_value = json_data if json_data is not None else {}
    return mock_resp


def _iso_settings(monkeypatch, **kwargs) -> Settings:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("DO_MODEL_ACCESS_KEY", raising=False)
    monkeypatch.delenv("MODEL_ACCESS_KEY", raising=False)
    get_settings.cache_clear()
    isolated = Settings(_env_file=None, **kwargs)
    monkeypatch.setattr(
        "aeo_mvp.visibility.openai_compatible.get_settings",
        lambda: isolated,
    )
    monkeypatch.setattr(
        "aeo_mvp.pipeline.orchestrator.get_settings",
        lambda: isolated,
    )
    return isolated


# --- A: success zero mentions → SUCCESS + zero ---


@pytest.mark.asyncio
async def test_a_openai_success_zero_mentions(monkeypatch):
    _iso_settings(monkeypatch, OPENAI_API_KEY=FAKE_KEY)
    content = "There are many project tools available in the market today."
    resp = _http_resp(json_data=_ok_completion(content))
    with patch(
        "aeo_mvp.visibility.openai_compatible.httpx.AsyncClient",
        return_value=_mock_client(resp),
    ):
        p = OpenAICompatibleProvider(api_key=FAKE_KEY)
        obs = await p.run_query("What is AcmeFlow?", context=_ctx())
    assert obs.detected_mention is False
    assert obs.provenance == "api_observation"
    assert obs.meta.get("error") is not True
    assert isinstance(obs.raw_response, str)


# --- B: success with mentions → SUCCESS + evidence ---


@pytest.mark.asyncio
async def test_b_openai_success_with_mentions(monkeypatch):
    _iso_settings(monkeypatch, OPENAI_API_KEY=FAKE_KEY)
    content = (
        "AcmeFlow is a popular project management platform. "
        "Learn more at https://acme.example/docs."
    )
    resp = _http_resp(json_data=_ok_completion(content))
    with patch(
        "aeo_mvp.visibility.openai_compatible.httpx.AsyncClient",
        return_value=_mock_client(resp),
    ):
        p = OpenAICompatibleProvider(api_key=FAKE_KEY)
        obs = await p.run_query("What is AcmeFlow?", context=_ctx())
    assert obs.detected_mention is True
    assert obs.detected_citation is True
    assert obs.provenance == "api_observation"
    assert "AcmeFlow" in (obs.raw_response or "")


# --- C: timeout → FAILED/provider-error, NOT SUCCESS ---


@pytest.mark.asyncio
async def test_c_timeout_raises_provider_error(monkeypatch):
    _iso_settings(monkeypatch, OPENAI_API_KEY=FAKE_KEY)
    mock_client = AsyncMock()
    mock_client.__aenter__.return_value = mock_client
    mock_client.__aexit__.return_value = None
    mock_client.post = AsyncMock(side_effect=httpx.ReadTimeout("timed out"))

    with patch(
        "aeo_mvp.visibility.openai_compatible.httpx.AsyncClient",
        return_value=mock_client,
    ):
        p = OpenAICompatibleProvider(api_key=FAKE_KEY)
        with pytest.raises(OpenAICompatibleError) as ei:
            await p.run_query("q", context=_ctx())
    err = ei.value
    assert err.category == "timeout"
    assert "provider-error" in str(err)
    assert "openai_compatible/timeout" in str(err)


# --- D: HTTP/API failure ---


@pytest.mark.asyncio
async def test_d_http_api_failure_raises(monkeypatch):
    _iso_settings(monkeypatch, OPENAI_API_KEY=FAKE_KEY)
    # Non-retryable 401 — no second call
    resp = _http_resp(status_code=401, text=f"unauthorized {FAKE_BEARER}")
    mock = _mock_client(resp)
    with patch(
        "aeo_mvp.visibility.openai_compatible.httpx.AsyncClient",
        return_value=mock,
    ):
        p = OpenAICompatibleProvider(api_key=FAKE_KEY)
        with pytest.raises(OpenAICompatibleError) as ei:
            await p.run_query("q", context=_ctx())
    assert ei.value.category == "upstream_http"
    assert ei.value.status_code == 401
    assert FAKE_KEY not in str(ei.value)
    assert FAKE_BEARER not in str(ei.value)
    assert mock.post.await_count == 1


@pytest.mark.asyncio
async def test_d_http_5xx_retries_once_then_fails(monkeypatch):
    _iso_settings(monkeypatch, OPENAI_API_KEY=FAKE_KEY)
    resp = _http_resp(status_code=503, text="unavailable")
    mock = _mock_client(resp)
    with patch(
        "aeo_mvp.visibility.openai_compatible.httpx.AsyncClient",
        return_value=mock,
    ):
        with patch("aeo_mvp.visibility.openai_compatible.asyncio.sleep", new_callable=AsyncMock):
            p = OpenAICompatibleProvider(api_key=FAKE_KEY)
            with pytest.raises(OpenAICompatibleError) as ei:
                await p.run_query("q", context=_ctx())
    assert ei.value.category == "upstream_http"
    assert ei.value.status_code == 503
    assert mock.post.await_count == 2


# --- E: malformed response ---


@pytest.mark.asyncio
async def test_e_malformed_json_raises(monkeypatch):
    _iso_settings(monkeypatch, OPENAI_API_KEY=FAKE_KEY)
    resp = _http_resp(json_raises=ValueError("No JSON"), text="<<<not-json>>>")
    with patch(
        "aeo_mvp.visibility.openai_compatible.httpx.AsyncClient",
        return_value=_mock_client(resp),
    ):
        p = OpenAICompatibleProvider(api_key=FAKE_KEY)
        with pytest.raises(OpenAICompatibleError) as ei:
            await p.run_query("q", context=_ctx())
    assert ei.value.category == "malformed_response"


@pytest.mark.asyncio
async def test_e_malformed_missing_choices_raises(monkeypatch):
    _iso_settings(monkeypatch, OPENAI_API_KEY=FAKE_KEY)
    resp = _http_resp(json_data={"id": "x", "choices": []})
    with patch(
        "aeo_mvp.visibility.openai_compatible.httpx.AsyncClient",
        return_value=_mock_client(resp),
    ):
        p = OpenAICompatibleProvider(api_key=FAKE_KEY)
        with pytest.raises(OpenAICompatibleError) as ei:
            await p.run_query("q", context=_ctx())
    assert ei.value.category == "malformed_response"


# --- F: missing/invalid config ---


def test_f_missing_credentials_explicit_failure(monkeypatch):
    _iso_settings(monkeypatch)
    with pytest.raises(OpenAICompatibleError) as ei:
        OpenAICompatibleProvider(api_key=None)
    assert ei.value.category == "missing_credentials"
    assert "OPENAI_API_KEY" in str(ei.value)


def test_f_select_provider_explicit_openai_without_key(monkeypatch):
    settings = _iso_settings(monkeypatch)
    orch = JobOrchestrator.__new__(JobOrchestrator)
    orch.settings = settings
    job = Job(
        id="j1",
        base_url="https://demo.example/",
        demo_mode=0,
        status="pending",
        options_json=json.dumps({"provider": "openai_compatible"}),
        created_at="t",
        updated_at="t",
    )
    with pytest.raises(OpenAICompatibleError) as ei:
        orch._select_provider(
            job,
            {"provider": "openai_compatible"},
            allow_paid_retrieval=False,
        )
    assert ei.value.category == "missing_credentials"


# --- G: exception does not produce synthetic/observed evidence ---


@pytest.mark.asyncio
async def test_g_exception_does_not_manufacture_evidence(monkeypatch):
    _iso_settings(monkeypatch, OPENAI_API_KEY=FAKE_KEY)
    mock_client = AsyncMock()
    mock_client.__aenter__.return_value = mock_client
    mock_client.__aexit__.return_value = None
    mock_client.post = AsyncMock(side_effect=RuntimeError(f"boom {FAKE_BEARER}"))

    with patch(
        "aeo_mvp.visibility.openai_compatible.httpx.AsyncClient",
        return_value=mock_client,
    ):
        p = OpenAICompatibleProvider(api_key=FAKE_KEY)
        with pytest.raises(OpenAICompatibleError) as ei:
            await p.run_query("q", context=_ctx())
    err = ei.value
    assert err.category == "internal_error"
    # Must not return a VisibilityObservation (raise, not soft empty)
    assert not isinstance(err, VisibilityObservation)
    assert FAKE_KEY not in str(err)


# --- H / I: API + logs never leak credentials ---


def test_h_i_redact_secrets_and_public_message():
    raw = f"Authorization: {FAKE_BEARER} api_key={FAKE_KEY}"
    cleaned = redact_secrets(raw)
    assert FAKE_KEY not in cleaned
    assert "Bearer [redacted]" in cleaned or "[redacted]" in cleaned

    err = OpenAICompatibleError(
        f"upstream failed with Authorization: {FAKE_BEARER}",
        category="upstream_http",
        status_code=401,
    )
    msg = err.public_message()
    assert FAKE_KEY not in msg
    assert "Authorization" not in msg or "[redacted]" in msg
    assert "provider-error: openai_compatible/upstream_http" in msg


@pytest.mark.asyncio
async def test_h_i_logs_never_contain_credentials(monkeypatch, caplog):
    _iso_settings(monkeypatch, OPENAI_API_KEY=FAKE_KEY)
    resp = _http_resp(
        status_code=500,
        text=f"server error Authorization: {FAKE_BEARER}",
    )
    with caplog.at_level(logging.WARNING, logger="aeo_mvp.visibility.openai_compatible"):
        with patch(
            "aeo_mvp.visibility.openai_compatible.httpx.AsyncClient",
            return_value=_mock_client(resp),
        ):
            with patch(
                "aeo_mvp.visibility.openai_compatible.asyncio.sleep",
                new_callable=AsyncMock,
            ):
                p = OpenAICompatibleProvider(api_key=FAKE_KEY)
                with pytest.raises(OpenAICompatibleError):
                    await p.run_query("q", context=_ctx())
    joined = "\n".join(r.getMessage() for r in caplog.records)
    assert FAKE_KEY not in joined
    assert FAKE_BEARER not in joined
    assert "provider_failure" in joined
    assert "category=upstream_http" in joined
    assert "job_id=job-test-1" in joined


# --- Job-level: provider error must NOT serialize SUCCESS with zero mentions ---


@pytest.mark.asyncio
async def test_regression_provider_error_job_failed_not_success_zero(
    db_session, monkeypatch
):
    """Exact regression: OpenAI error → job failed, not completed + zero mentions."""
    settings = _iso_settings(monkeypatch, OPENAI_API_KEY=FAKE_KEY, AEO_DEMO_MODE=False)

    async def boom(self, query, *, context):
        raise OpenAICompatibleError(
            f"upstream HTTP 500 with {FAKE_BEARER}",
            category="upstream_http",
            status_code=500,
        )

    job = create_job_record(
        db_session,
        "https://demo.example/",
        demo_mode=False,
        options={
            "provider": "openai_compatible",
            "runs_per_prompt": 1,
            "max_pages": 1,
            "discovery_only": False,
            "content_optimization": False,
        },
    )
    job.demo_mode = 0
    db_session.commit()

    with (
        patch("aeo_mvp.pipeline.orchestrator.crawl_site", side_effect=_fake_crawl),
        patch.object(OpenAICompatibleProvider, "run_query", boom),
    ):
        orch = JobOrchestrator(db_session)
        orch.settings = settings
        with pytest.raises(OpenAICompatibleError) as ei:
            await orch.run(job.id)

    db_session.refresh(job)
    assert ei.value.category == "upstream_http"
    assert job.status == "failed"
    assert job.status != "completed"
    assert job.error_message is not None
    assert "provider-error" in job.error_message
    assert "openai_compatible/upstream_http" in job.error_message
    assert FAKE_KEY not in (job.error_message or "")
    assert FAKE_BEARER not in (job.error_message or "")
    # No successful observation rows that would look like zero-mention evidence
    rows = (
        db_session.query(VisObsRow)
        .filter(VisObsRow.job_id == job.id)
        .all()
    )
    assert rows == []


@pytest.mark.asyncio
async def test_valid_empty_evidence_remains_success(db_session, monkeypatch):
    """Valid SUCCESS with zero mentions stays distinguishable from provider failure."""
    settings = _iso_settings(monkeypatch, OPENAI_API_KEY=FAKE_KEY, AEO_DEMO_MODE=False)

    async def empty_ok(self, query, *, context):
        return VisibilityObservation(
            provider_name="openai_compatible",
            engine_label="openai_compatible:test",
            query=query,
            prompt_id=context.prompt_id,
            run_index=context.run_index,
            observed_at=datetime.now(timezone.utc),
            raw_response="No brands mentioned here.",
            raw_storage_permitted=True,
            detected_mention=False,
            detected_citation=False,
            cited_urls=[],
            extraction_methodology="test",
            provenance="api_observation",
            meta={"error": False},
            model_id="test",
            retrieval_enabled=False,
            experiment_kind="llm_mention",
        )

    job = create_job_record(
        db_session,
        "https://demo.example/",
        demo_mode=False,
        options={
            "provider": "openai_compatible",
            "runs_per_prompt": 1,
            "max_pages": 1,
            "content_optimization": False,
        },
    )
    job.demo_mode = 0
    db_session.commit()

    with (
        patch("aeo_mvp.pipeline.orchestrator.crawl_site", side_effect=_fake_crawl),
        patch.object(OpenAICompatibleProvider, "run_query", empty_ok),
    ):
        orch = JobOrchestrator(db_session)
        orch.settings = settings
        await orch.run(job.id)

    db_session.refresh(job)
    assert job.status == "completed"
    assert job.error_message is None
    rows = (
        db_session.query(VisObsRow)
        .filter(VisObsRow.job_id == job.id)
        .all()
    )
    assert len(rows) >= 1
    assert all(r.detected_mention == 0 for r in rows)


# --- J: Demo provider unchanged ---


@pytest.mark.asyncio
async def test_j_demo_provider_unchanged():
    p = DemoProvider()
    obs = await p.run_query(
        "What is AcmeFlow?",
        context=_ctx(prompt_id="ps1_brand", run_index=0),
    )
    assert obs.provider_name == "demo"
    assert obs.provenance == "synthetic_demo"
    assert obs.retrieval_enabled is False


# --- K: DigitalOcean + P0-1 gate unchanged (smoke of selection) ---


def test_k_do_gate_still_blocks_without_opt_in(monkeypatch):
    from aeo_mvp.visibility.digitalocean_web_search import DigitalOceanWebSearchError

    settings = _iso_settings(
        monkeypatch,
        DO_MODEL_ACCESS_KEY="do-test-key-not-real",
    )
    orch = JobOrchestrator.__new__(JobOrchestrator)
    orch.settings = settings
    job = Job(
        id="j-do",
        base_url="https://demo.example/",
        demo_mode=0,
        status="pending",
        options_json=json.dumps({"provider": "digitalocean_web_search"}),
        created_at="t",
        updated_at="t",
    )
    with pytest.raises(DigitalOceanWebSearchError, match="paid_retrieval_opt_in"):
        orch._select_provider(
            job,
            {"provider": "digitalocean_web_search"},
            allow_paid_retrieval=False,
        )
    assert (
        JobOrchestrator._allow_paid_do_retrieval(
            paid_opt_in=False, paid_retrieval_ready=True
        )
        is False
    )


# --- L: happy-path / content-optimization path still imports cleanly ---


def test_l_content_optimization_module_importable():
    from aeo_mvp.content import gaps, brief, pipeline  # noqa: F401

    assert gaps is not None
    assert brief is not None
    assert pipeline is not None


def test_openai_provider_requires_key_updated(monkeypatch):
    """Replacement for legacy ValueError skip test."""
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    get_settings.cache_clear()
    with pytest.raises(OpenAICompatibleError) as ei:
        OpenAICompatibleProvider(api_key=None)
    assert ei.value.category == "missing_credentials"
