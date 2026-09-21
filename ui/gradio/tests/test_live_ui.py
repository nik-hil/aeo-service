"""Opt-in live UI path. Default pytest must not run this.

Set ``AEO_LIVE_UI_TEST=true`` plus ``AEO_API_BASE_URL`` and ``AEO_API_KEY``.
The API process must already be running. This does not start a server and
does not use demo mode.
"""

from __future__ import annotations

import os
import time

import httpx
import pytest

from app import run_analysis
from services.adapters import AnalysisState
from services.api_client import AeoApiClient

LIVE = os.environ.get("AEO_LIVE_UI_TEST") == "true"
TARGET = (
    "https://nik-hil.hashnode.dev/agents-zero-to-hero-1-building-an-ai-agent-from-scratch-with-tool-calling"
)

pytestmark = pytest.mark.skipif(
    not LIVE,
    reason="set AEO_LIVE_UI_TEST=true to exercise the live API/UI path",
)


def test_live_hashnode_single_page_ui_path():
    base = os.environ.get("AEO_API_BASE_URL") or ""
    key = os.environ.get("AEO_API_KEY") or ""
    assert base, "AEO_API_BASE_URL is required when AEO_LIVE_UI_TEST=true"
    assert key, "AEO_API_KEY is required when AEO_LIVE_UI_TEST=true"
    os.environ.setdefault("AEO_UI_JOB_TIMEOUT", "240")

    unauth = httpx.post(
        f"{base.rstrip('/')}/api/v1/jobs",
        json={"url": TARGET, "demo_mode": False, "options": {"max_pages": 1}},
        timeout=30.0,
    )
    assert unauth.status_code == 401

    client = AeoApiClient(base_url=base, api_key=key)
    health = client.health()
    assert health.get("status") == "ok"

    t0 = time.perf_counter()
    completed = []
    statuses = []
    for out in run_analysis(TARGET, "Single page URL", False, True, AnalysisState()):
        statuses.append(out[1])
        if out[0].report:
            completed.append((time.perf_counter() - t0, out))
    elapsed = time.perf_counter() - t0
    assert completed, f"no report yield; last status={statuses[-1] if statuses else None}"
    state = completed[-1][1][0]
    report = state.report or {}
    assert report.get("demo_mode") is False
    assert "hashnode.dev" in str(report.get("base_url") or "")
    crawl = report.get("crawl") or {}
    page_id = None
    pages = (state.pages or {}).get("pages") or []
    if pages:
        page_id = pages[0].get("id")
    enrich_s = None
    if page_id and state.job_id:
        t_en = time.perf_counter()
        client.content_optimization(job_id=state.job_id, page_id=str(page_id), content_draft=True)
        enrich_s = time.perf_counter() - t_en
    print(
        "LIVE_UI "
        f"job_to_first_report_s={completed[0][0]:.3f} "
        f"job_to_final_yield_s={completed[-1][0]:.3f} "
        f"generator_s={elapsed:.3f} "
        f"completed_yields={len(completed)} "
        f"crawl={crawl} "
        f"pages_crawled={report.get('pages_crawled')} "
        f"content_optimization_s={enrich_s}"
    )
