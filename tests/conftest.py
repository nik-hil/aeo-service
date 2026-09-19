"""Shared pytest fixtures."""

from __future__ import annotations

import asyncio
import os

import pytest
from fastapi.testclient import TestClient

# Use isolated in-memory-ish sqlite file per test session
os.environ.setdefault("AEO_DATABASE_URL", "sqlite:///./test_aeo_mvp.db")
os.environ["AEO_DEMO_MODE"] = "false"

from aeo_mvp.db.session import get_session_factory, init_db, reset_engine  # noqa: E402
from aeo_mvp.pipeline.orchestrator import JobOrchestrator, create_job_record  # noqa: E402

# Test-only bearer secret — never load real .env API keys into auth assertions.
TEST_API_KEY = "test-aeo-api-key-not-real"


def _install_isolated_settings(monkeypatch, **kwargs):
    """Settings from constructor only (not .env) — same isolation pattern as P0-1."""
    from aeo_mvp.config import Settings, get_settings

    get_settings.cache_clear()
    isolated = Settings(_env_file=None, **kwargs)

    def _fake_get_settings():
        return isolated

    # Preserve cache_clear for fixture teardown while get_settings is patched.
    _fake_get_settings.cache_clear = get_settings.cache_clear  # type: ignore[attr-defined]

    monkeypatch.setattr("aeo_mvp.config.get_settings", _fake_get_settings)
    monkeypatch.setattr("aeo_mvp.security.api_auth.get_settings", _fake_get_settings)
    monkeypatch.setattr("aeo_mvp.api.routes.get_settings", _fake_get_settings)
    return isolated


@pytest.fixture()
def db_session(tmp_path, monkeypatch):
    db_path = tmp_path / "aeo.db"
    url = f"sqlite:///{db_path}"
    monkeypatch.setenv("AEO_DATABASE_URL", url)
    reset_engine()
    from aeo_mvp.config import get_settings

    get_settings.cache_clear()
    init_db(url)
    factory = get_session_factory(url)
    session = factory()
    try:
        yield session
        session.commit()
    finally:
        session.close()
        reset_engine()
        get_settings.cache_clear()


@pytest.fixture()
def api_key(monkeypatch):
    """Default auth config for API tests (isolated from .env)."""
    monkeypatch.delenv("AEO_API_KEY", raising=False)
    monkeypatch.delenv("AEO_ALLOW_UNAUTHENTICATED", raising=False)
    return TEST_API_KEY


@pytest.fixture()
def client(tmp_path, monkeypatch, api_key):
    db_path = tmp_path / "api.db"
    url = f"sqlite:///{db_path}"
    monkeypatch.setenv("AEO_DATABASE_URL", url)
    reset_engine()
    _install_isolated_settings(
        monkeypatch,
        AEO_DATABASE_URL=url,
        AEO_API_KEY=api_key,
        AEO_ALLOW_UNAUTHENTICATED=False,
        AEO_ENVIRONMENT="test",
    )
    init_db(url)
    from aeo_mvp.api.app import create_app

    app = create_app()
    with TestClient(app) as c:
        c.headers.update({"Authorization": f"Bearer {api_key}"})
        yield c
    reset_engine()
    from aeo_mvp.config import get_settings

    get_settings.cache_clear()


def run_demo_job(session):
    job = create_job_record(
        session,
        "https://demo.example/",
        demo_mode=True,
        options={"provider": "demo", "runs_per_prompt": 3},
    )
    session.commit()
    asyncio.get_event_loop().run_until_complete(JobOrchestrator(session).run(job.id))
    session.commit()
    session.refresh(job)
    return job
