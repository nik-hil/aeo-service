"""Opt-in live UI path. Default pytest must not run this.

Set ``AEO_LIVE_UI_TEST=true`` plus ``AEO_API_BASE_URL`` and ``AEO_API_KEY``.
The API process must already be running. This does not start a server and
does not use demo mode.
"""

from __future__ import annotations

import asyncio
import os
import time
from urllib.parse import urlparse

import httpx
import pytest

import app as app_mod
from app import on_select_page, run_analysis
from services.adapters import AnalysisState, adapt_overview, overview_markdown
from services.api_client import AeoApiClient
from services.enrichment import fetch_content_optimization, needs_page_enrichment
from views.analyze import build_job_options

LIVE = os.environ.get("AEO_LIVE_UI_TEST") == "true"
TARGET = (
    "https://nik-hil.hashnode.dev/agents-zero-to-hero-1-building-an-ai-agent-from-scratch-with-tool-calling"
)
HOST = "nik-hil.hashnode.dev"

pytestmark = pytest.mark.skipif(
    not LIVE,
    reason="set AEO_LIVE_UI_TEST=true to exercise the live API/UI path",
)


class _TimingClient(AeoApiClient):
    def __init__(self) -> None:
        super().__init__()
        self.create_s = 0.0
        self.report_s = 0.0
        self.t_created = 0.0
        self.t_completed = 0.0
        self.t_report = 0.0

    def create_job(self, url, *, demo_mode=False, options=None):
        t = time.perf_counter()
        job = super().create_job(url, demo_mode=demo_mode, options=options)
        self.create_s = time.perf_counter() - t
        self.t_created = time.perf_counter()
        return job

    def get_job(self, job_id):
        payload = super().get_job(job_id)
        if payload.get("status") == "completed" and self.t_completed == 0.0:
            self.t_completed = time.perf_counter()
        return payload

    def get_report(self, job_id):
        t = time.perf_counter()
        payload = super().get_report(job_id)
        self.report_s = time.perf_counter() - t
        self.t_report = time.perf_counter()
        return payload


def test_live_hashnode_ui_path():
    base = os.environ.get("AEO_API_BASE_URL") or ""
    key = os.environ.get("AEO_API_KEY") or ""
    assert base, "AEO_API_BASE_URL is required when AEO_LIVE_UI_TEST=true"
    assert key, "AEO_API_KEY is required when AEO_LIVE_UI_TEST=true"
    os.environ.setdefault("AEO_UI_JOB_TIMEOUT", "300")

    no_auth = httpx.post(
        f"{base.rstrip('/')}/api/v1/jobs",
        json={"url": TARGET, "demo_mode": False, "options": {"max_pages": 1}},
        timeout=30.0,
    )
    bad_auth = httpx.post(
        f"{base.rstrip('/')}/api/v1/jobs",
        json={"url": TARGET, "demo_mode": False, "options": {"max_pages": 1}},
        headers={"Authorization": "Bearer wrong-key"},
        timeout=30.0,
    )
    health = httpx.get(f"{base.rstrip('/')}/health", timeout=15.0)
    assert no_auth.status_code == 401
    assert bad_auth.status_code == 401
    assert health.status_code == 200

    timer = _TimingClient()
    app_mod._client = lambda: timer
    first_report_s = None
    final_s = None
    t0 = time.perf_counter()
    final_state = None
    completed = 0
    for out in run_analysis(TARGET, "Single page URL", False, True, AnalysisState()):
        if "## Analysis overview" not in str(out[3]):
            continue
        completed += 1
        now = time.perf_counter() - t0
        if first_report_s is None:
            first_report_s = now
        final_s = now
        final_state = out[0]
    assert final_state is not None and final_state.report
    report = final_state.report
    assert report.get("demo_mode") is False
    co = report.get("content_optimization") or {}
    assert co.get("paid_retrieval") is False
    assert co.get("paid_llm") is False
    crawl = report.get("crawl") or {}
    vm = adapt_overview(report, mode="single", opportunity_count=0)
    stage_a_after_report = None
    if timer.t_report and first_report_s is not None:
        stage_a_after_report = (t0 + first_report_s) - timer.t_report
    pipeline_s = None
    if timer.t_created and timer.t_completed:
        pipeline_s = timer.t_completed - timer.t_created

    plain = AeoApiClient()
    page = (final_state.pages or {}).get("pages") or []
    page_id = str(page[0]["id"]) if page else ""
    t_en = time.perf_counter()
    enrich = plain.content_optimization(
        job_id=str(final_state.job_id), page_id=page_id, content_draft=True
    )
    enrich_s = time.perf_counter() - t_en
    assert (enrich.get("page_intelligence") or {}).get("url")

    opts = build_job_options(mode="multi", use_demo=False, include_draft=True)
    assert opts["max_pages"] == 20 and opts["max_depth"] == 2
    t_multi = time.perf_counter()
    job = plain.create_job(TARGET, demo_mode=False, options=opts)
    deadline = time.perf_counter() + 300
    status = ""
    while time.perf_counter() < deadline:
        payload = plain.get_job(job.id)
        status = str(payload.get("status") or "")
        if status in {"completed", "failed"}:
            break
        time.sleep(0.45)
    multi_s = time.perf_counter() - t_multi
    assert status == "completed", payload.get("error_message")
    multi_report = plain.get_report(job.id)
    multi_pages = plain.get_pages(job.id)
    rows = multi_pages.get("pages") or []
    hosts = sorted({urlparse(str(p.get("url") or "")).netloc for p in rows})
    external = [h for h in hosts if h and h != HOST]
    multi_vm = adapt_overview(multi_report, mode="multi", opportunity_count=0)
    multi_md = overview_markdown(multi_vm)
    assert "same-host" in multi_md.lower()
    assert "entire" not in multi_md.lower()
    assert "series" not in multi_md.lower()
    assert external == []
    assert (multi_report.get("content_optimization") or {}).get("paid_retrieval") is False

    primary = str((multi_report.get("page_intelligence") or {}).get("url") or "")
    secondary = next(
        p
        for p in rows
        if needs_page_enrichment(multi_report, page_url=p.get("url"), page_id=p.get("id"))
    )
    ui_state = AnalysisState(
        job_id=job.id,
        report=multi_report,
        pages=multi_pages,
        mode="multi",
    )
    real_fetch = fetch_content_optimization
    posts = {"n": 0}

    async def counting_fetch(client, *, job_id, page_id, content_draft=True):
        posts["n"] += 1
        return await real_fetch(
            client, job_id=job_id, page_id=page_id, content_draft=content_draft
        )

    app_mod.fetch_content_optimization = counting_fetch

    async def _secondary():
        url = str(secondary["url"])
        t_a = time.perf_counter()
        gen = on_select_page(url, ui_state)
        first = await gen.__anext__()
        stage_a = time.perf_counter() - t_a
        assert "loading" in (first[3] or "").lower()
        assert posts["n"] == 0
        t_b = time.perf_counter()
        last = first
        async for out in gen:
            last = out
        stage_b = time.perf_counter() - t_b
        assert posts["n"] == 1
        assert "Could not load" not in (last[3] or "")
        t_re = time.perf_counter()
        resent = []
        async for out in on_select_page(url, ui_state):
            resent.append(out)
        reselect_s = time.perf_counter() - t_re
        assert posts["n"] == 1
        assert len(resent) == 1

        async def drain():
            outs = []
            async for out in on_select_page(url, ui_state):
                outs.append(out)
            return outs

        # Cache is SUCCESS, so a pair of reselects must not POST.
        # Force a fresh in-flight race on another secondary page.
        other = next(
            p
            for p in rows
            if p.get("id") != secondary.get("id")
            and needs_page_enrichment(multi_report, page_url=p.get("url"), page_id=p.get("id"))
        )
        before = posts["n"]
        t_c = time.perf_counter()
        left, right = await asyncio.gather(drain_url(str(other["url"])), drain_url(str(other["url"])))
        concurrent_s = time.perf_counter() - t_c
        assert posts["n"] == before + 1
        assert left[-1][2] == right[-1][2]
        return {
            "url": url,
            "stage_a_s": stage_a,
            "stage_b_s": stage_b,
            "posts": 1,
            "reselect_s": reselect_s,
            "reselect_posts": 0,
            "concurrent_url": other["url"],
            "concurrent_s": concurrent_s,
            "concurrent_posts": 1,
        }

    async def drain_url(url: str):
        outs = []
        async for out in on_select_page(url, ui_state):
            outs.append(out)
        return outs

    secondary_stats = asyncio.run(_secondary())

    t_404 = time.perf_counter()
    missing = asyncio.run(
        fetch_content_optimization(
            plain, job_id=job.id, page_id="not-a-real-page", content_draft=True
        )
    )
    missing_s = time.perf_counter() - t_404
    assert missing.status.value == "error"
    assert "not found" in (missing.error_message or "").lower()
    assert "Traceback" not in (missing.error_message or "")

    print(
        "LIVE_SINGLE "
        f"create_s={timer.create_s:.4f} "
        f"to_completed_s={pipeline_s:.4f} "
        f"report_get_s={timer.report_s:.4f} "
        f"report_to_first_yield_s={stage_a_after_report:.4f} "
        f"first_yield_s={first_report_s:.4f} "
        f"final_yield_s={final_s:.4f} "
        f"completed_yields={completed} "
        f"enrich_s={enrich_s:.4f} "
        f"discovered={crawl.get('discovered')} fetched={crawl.get('fetched')} "
        f"errors={crawl.get('errors')} status={crawl.get('status')} partial={vm.crawl_partial}"
    )
    print(
        "LIVE_MULTI "
        f"total_s={multi_s:.4f} "
        f"discovered={multi_report.get('crawl', {}).get('discovered')} "
        f"fetched={multi_report.get('crawl', {}).get('fetched')} "
        f"errors={multi_report.get('crawl', {}).get('errors')} "
        f"status={multi_report.get('crawl', {}).get('status')} "
        f"partial={multi_vm.crawl_partial} hosts={hosts} external={external}"
    )
    print(
        "LIVE_SECONDARY "
        f"stage_a_s={secondary_stats['stage_a_s']:.4f} "
        f"stage_b_s={secondary_stats['stage_b_s']:.4f} "
        f"posts={secondary_stats['posts']} "
        f"reselect_s={secondary_stats['reselect_s']:.4f} "
        f"concurrent_posts={secondary_stats['concurrent_posts']} "
        f"concurrent_s={secondary_stats['concurrent_s']:.4f} "
        f"primary={primary}"
    )
    print(
        "LIVE_ERRORS "
        f"missing_page_s={missing_s:.4f} status={missing.status.value} "
        f"no_auth={no_auth.status_code} bad_auth={bad_auth.status_code} health={health.status_code}"
    )
