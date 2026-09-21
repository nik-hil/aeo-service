"""Async page enrichment tests — client, cache, race, errors."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock

import httpx
import pytest

from app import detail_panels, on_select_page, run_analysis
from fixture_report import OPT_PAYLOAD_ABOUT, PAGES_PAYLOAD, SAMPLE_REPORT, SYNTHETIC_20_PAGES
from services.adapters import (
    UI_MULTI_MAX_PAGES,
    AnalysisState,
    adapt_pages,
    comparison_markdown,
    pages_table,
    truncate_url,
)
from services.api_client import AeoApiClient, AeoApiError, user_safe_enrichment_error
from services.enrichment import (
    EnrichmentCache,
    EnrichmentEntry,
    EnrichmentStatus,
    fetch_content_optimization,
    is_stale,
    needs_page_enrichment,
    next_selection_id,
)


@pytest.mark.asyncio
async def test_content_optimization_async_auth_payload_and_endpoint():
    seen: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["path"] = request.url.path
        seen["method"] = request.method
        seen["auth"] = request.headers.get("authorization")
        seen["body"] = request.read()
        return httpx.Response(200, json=OPT_PAYLOAD_ABOUT)

    client = AeoApiClient(
        base_url="http://test",
        api_key="secret-key",
        async_transport=httpx.MockTransport(handler),
    )
    out = await client.content_optimization_async(
        job_id="job-1", page_id="p2", content_draft=True
    )
    assert out["page_intelligence"]["url"] == "https://demo.example/about"
    assert seen["path"] == "/api/v1/content-optimization"
    assert seen["method"] == "POST"
    assert seen["auth"] == "Bearer secret-key"
    import json

    body = json.loads(seen["body"])
    assert body["job_id"] == "job-1"
    assert body["page_id"] == "p2"
    assert body["content_draft"] is True


@pytest.mark.asyncio
async def test_content_optimization_async_errors():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={"detail": "page missing"})

    client = AeoApiClient(
        base_url="http://test",
        api_key="k",
        async_transport=httpx.MockTransport(handler),
    )
    with pytest.raises(AeoApiError) as ei:
        await client.content_optimization_async(job_id="j", page_id="x")
    assert ei.value.status_code == 404
    assert "not found" in user_safe_enrichment_error(ei.value).lower()


@pytest.mark.asyncio
async def test_fetch_maps_timeout_and_500():
    def timeout_handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("slow")

    client = AeoApiClient(
        base_url="http://test",
        api_key="k",
        async_transport=httpx.MockTransport(timeout_handler),
    )
    entry = await fetch_content_optimization(client, job_id="j", page_id="p")
    assert entry.status == EnrichmentStatus.ERROR
    assert "timed out" in (entry.error_message or "").lower()

    def boom(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"detail": "nope"})

    client2 = AeoApiClient(
        base_url="http://test",
        api_key="k",
        async_transport=httpx.MockTransport(boom),
    )
    entry2 = await fetch_content_optimization(client2, job_id="j", page_id="p")
    assert entry2.status == EnrichmentStatus.ERROR
    assert "unavailable" in (entry2.error_message or "").lower()


@pytest.mark.asyncio
async def test_on_select_page_immediate_then_enrich(monkeypatch):
    state = AnalysisState(
        job_id="job-demo-1",
        report=SAMPLE_REPORT,
        pages=PAGES_PAYLOAD,
        selected_page_url="https://demo.example/",
    )
    assert needs_page_enrichment(
        SAMPLE_REPORT, page_url="https://demo.example/about", page_id="p2"
    )

    calls = {"n": 0}

    async def fake_fetch(client, *, job_id, page_id, content_draft=True):
        calls["n"] += 1
        await asyncio.sleep(0.05)
        return EnrichmentEntry(status=EnrichmentStatus.SUCCESS, payload=OPT_PAYLOAD_ABOUT)

    monkeypatch.setattr("app.fetch_content_optimization", fake_fetch)

    gen = on_select_page("https://demo.example/about", state)
    first = await gen.__anext__()
    # Stage A: loading copy, observed header/before present
    assert "loading" in first[3].lower() or "Additional optimization" in first[3]
    assert first[1]  # header html
    assert "observed" in first[2].lower() or "CURRENT" in first[2] or first[2]

    second = await gen.__anext__()
    assert calls["n"] == 1
    assert "About AcmeFlow" in second[2] or "About" in second[2]
    assert "skeleton" in second[4].lower() or "Brief" in second[4] or "add_entity" in second[4]
    assert "Optimized Page" not in second[4]
    # exhausted
    with pytest.raises(StopAsyncIteration):
        await gen.__anext__()


@pytest.mark.asyncio
async def test_race_a_then_b_discards_late_a(monkeypatch):
    state = AnalysisState(
        job_id="job-demo-1",
        report=SAMPLE_REPORT,
        pages=PAGES_PAYLOAD,
    )
    release_a = asyncio.Event()
    order: list[str] = []

    async def fake_fetch(client, *, job_id, page_id, content_draft=True):
        order.append(page_id)
        if page_id == "p2":
            await release_a.wait()
            return EnrichmentEntry(
                status=EnrichmentStatus.SUCCESS,
                payload={
                    **OPT_PAYLOAD_ABOUT,
                    "page_intelligence": {
                        **OPT_PAYLOAD_ABOUT["page_intelligence"],
                        "title": "LATE-A-SHOULD-NOT-WIN",
                    },
                },
            )
        return EnrichmentEntry(
            status=EnrichmentStatus.SUCCESS,
            payload={
                "page_intelligence": {
                    "url": "https://demo.example/",
                    "title": "Home-B-wins",
                    "heading_outline": ["Home"],
                    "answer_blocks": [],
                    "word_count": 10,
                },
                "optimization_briefs": [],
                "content_drafts": [],
                "content_gaps": [],
            },
        )

    monkeypatch.setattr("app.fetch_content_optimization", fake_fetch)

    # Start A (about / p2)
    gen_a = on_select_page("https://demo.example/about", state)
    stage_a = await gen_a.__anext__()
    assert "loading" in stage_a[3].lower() or "Additional" in stage_a[3]

    # Switch to B (home) — home usually does not need enrichment; force needs by
    # temporarily using about-like mismatch: select about again after priming token.
    # Instead select a page that needs enrich: use about as A, then use a synthetic
    # secondary path. Home matches PI so won't call fetch. Use about → then reselect
    # about after B... Spec: A selected → B selected → A finishes late must NOT overwrite B.
    # Make B also need enrichment by pointing PI away.
    state.report = {
        **SAMPLE_REPORT,
        "page_intelligence": {**SAMPLE_REPORT["page_intelligence"], "url": "https://other.example/"},
    }
    # Both pages need enrichment now.
    gen_b = on_select_page("https://demo.example/", state)
    stage_b1 = await gen_b.__anext__()
    assert "loading" in stage_b1[3].lower() or "Additional" in stage_b1[3]
    stage_b2 = await gen_b.__anext__()
    assert "Home-B-wins" in stage_b2[2]
    b_selection = state.selection_id

    # Let A finish — should discard (no further yield or no overwrite)
    release_a.set()
    late = []
    try:
        while True:
            late.append(await gen_a.__anext__())
    except StopAsyncIteration:
        pass
    # Either no Stage B yield from A, or if yielded it must not become current selection content
    assert state.selection_id == b_selection
    assert state.selected_page_url == "https://demo.example/"
    if late:
        assert "LATE-A-SHOULD-NOT-WIN" not in late[-1][2]


@pytest.mark.asyncio
async def test_cache_a_b_a_one_enrich_call(monkeypatch):
    state = AnalysisState(
        job_id="job-demo-1",
        report={
            **SAMPLE_REPORT,
            "page_intelligence": {**SAMPLE_REPORT["page_intelligence"], "url": "https://other/"},
        },
        pages=PAGES_PAYLOAD,
    )
    calls = {"n": 0}

    async def fake_fetch(client, *, job_id, page_id, content_draft=True):
        calls["n"] += 1
        await asyncio.sleep(0.01)
        if page_id == "p2":
            return EnrichmentEntry(status=EnrichmentStatus.SUCCESS, payload=OPT_PAYLOAD_ABOUT)
        return EnrichmentEntry(
            status=EnrichmentStatus.SUCCESS,
            payload={
                "page_intelligence": {
                    "url": "https://demo.example/",
                    "title": "Home",
                    "heading_outline": ["H"],
                    "answer_blocks": [],
                    "word_count": 1,
                }
            },
        )

    monkeypatch.setattr("app.fetch_content_optimization", fake_fetch)

    async def drain(url):
        outs = []
        async for o in on_select_page(url, state):
            outs.append(o)
        return outs

    await drain("https://demo.example/about")
    assert calls["n"] == 1
    await drain("https://demo.example/")
    assert calls["n"] == 2
    outs = await drain("https://demo.example/about")
    assert calls["n"] == 2  # cache hit
    assert len(outs) == 1  # instant single yield
    assert "About" in outs[0][2]


@pytest.mark.asyncio
async def test_rapid_nav_final_page_wins(monkeypatch):
    state = AnalysisState(
        job_id="job-demo-1",
        report={
            **SAMPLE_REPORT,
            "page_intelligence": {**SAMPLE_REPORT["page_intelligence"], "url": "https://other/"},
        },
        pages=PAGES_PAYLOAD,
    )
    gate = {"p2": asyncio.Event(), "p1": asyncio.Event()}

    async def fake_fetch(client, *, job_id, page_id, content_draft=True):
        await gate[page_id].wait()
        title = "FINAL-ABOUT" if page_id == "p2" else "FINAL-HOME"
        url = "https://demo.example/about" if page_id == "p2" else "https://demo.example/"
        return EnrichmentEntry(
            status=EnrichmentStatus.SUCCESS,
            payload={
                "page_intelligence": {
                    "url": url,
                    "title": title,
                    "heading_outline": ["x"],
                    "answer_blocks": [],
                    "word_count": 1,
                }
            },
        )

    monkeypatch.setattr("app.fetch_content_optimization", fake_fetch)

    gen1 = on_select_page("https://demo.example/", state)
    await gen1.__anext__()
    gen2 = on_select_page("https://demo.example/about", state)
    await gen2.__anext__()
    gate["p1"].set()
    gate["p2"].set()
    # drain home (may discard)
    try:
        while True:
            await gen1.__anext__()
    except StopAsyncIteration:
        pass
    last = None
    try:
        while True:
            last = await gen2.__anext__()
    except StopAsyncIteration:
        pass
    assert last is not None
    assert "FINAL-ABOUT" in last[2]
    assert state.selected_page_url == "https://demo.example/about"


@pytest.mark.asyncio
async def test_enrich_error_leaves_page_usable(monkeypatch):
    state = AnalysisState(
        job_id="job-demo-1",
        report=SAMPLE_REPORT,
        pages=PAGES_PAYLOAD,
    )

    async def fake_fetch(client, *, job_id, page_id, content_draft=True):
        return EnrichmentEntry(
            status=EnrichmentStatus.ERROR,
            error_message="Optimization analysis is not available for this page (not found).",
        )

    monkeypatch.setattr("app.fetch_content_optimization", fake_fetch)
    outs = []
    async for o in on_select_page("https://demo.example/about", state):
        outs.append(o)
    assert len(outs) >= 2
    final = outs[-1]
    assert final[1]  # header still present
    assert "not found" in final[3].lower() or "Could not load" in final[3]
    assert final[2]  # before/observed still rendered


def test_selection_token_helpers():
    assert next_selection_id(0) == 1
    assert next_selection_id(3) == 4
    assert is_stale(2, 1) is True
    assert is_stale(2, 2) is False


def test_multi_max_pages_in_request(monkeypatch):
    captured = {}

    class FakeClient:
        def create_job(self, url, *, demo_mode=False, options=None):
            from services.api_client import JobRef

            captured["options"] = options
            return JobRef(id="job-1", status="pending", base_url=url, demo_mode=demo_mode)

        def get_job(self, job_id):
            return {"id": job_id, "status": "completed", "base_url": "https://demo.example/"}

        def get_report(self, job_id):
            return SAMPLE_REPORT

        def get_pages(self, job_id):
            return PAGES_PAYLOAD

    monkeypatch.setattr("app._client", lambda: FakeClient())
    list(
        run_analysis(
            "https://demo.example/",
            "Multi-page crawl seed (same-host from seed)",
            True,
            True,
            AnalysisState(),
        )
    )
    assert captured["options"]["max_pages"] == UI_MULTI_MAX_PAGES
    assert UI_MULTI_MAX_PAGES >= 20
    assert UI_MULTI_MAX_PAGES <= 25


def test_synthetic_20_page_table():
    rows = adapt_pages(SYNTHETIC_20_PAGES)
    assert len(rows) == 20
    assert SYNTHETIC_20_PAGES.get("synthetic") is True
    table = pages_table(rows)
    assert len(table) == 20
    assert len(table[0][1]) <= 64
    assert "…" in truncate_url("https://x.com/" + ("a" * 100))



def test_comparison_honest_labels():
    md = comparison_markdown(SAMPLE_REPORT, "https://demo.example/")
    assert "CURRENT" in md
    assert "RECOMMENDED" in md
    assert "Optimized Page" not in md
    assert "not a live browser render" in md.lower()


def test_enrichment_cache_session_scoped():
    from copy import deepcopy

    c = EnrichmentCache()
    c.set("j1", "p1", EnrichmentEntry(status=EnrichmentStatus.SUCCESS, payload={"a": 1}))
    assert c.get("j1", "p1").payload == {"a": 1}
    role, token = c.claim("j1", "p2")
    assert role == "owner" and token is not None
    assert c.claim("j1", "p2")[0] == "in_flight"
    assert c.pop_if_loading("j1", "p2", token + 1) is False
    assert c.get("j1", "p2").status == EnrichmentStatus.LOADING
    assert c.pop_if_loading("j1", "p2", token) is True
    assert c.get("j1", "p2") is None
    c.set("j1", "p1", EnrichmentEntry(status=EnrichmentStatus.SUCCESS, payload={"a": 1}))
    cloned = deepcopy(c)
    assert cloned.get("j1", "p1").payload == {"a": 1}
    assert cloned is not c
    c.clear()
    assert c.get("j1", "p1") is None
    assert cloned.get("j1", "p1") is not None


def _mismatch_report() -> dict:
    return {
        **SAMPLE_REPORT,
        "page_intelligence": {
            **SAMPLE_REPORT["page_intelligence"],
            "url": "https://other.example/not-selected",
        },
    }


def _completed_yields(outputs: list) -> list:
    return [out for out in outputs if "## Analysis overview" in str(out[3])]


class _ImmediateJob:
    def __init__(self, report: dict):
        self.report = report

    def create_job(self, url, *, demo_mode=False, options=None):
        from services.api_client import JobRef

        return JobRef(id="job-1", status="pending", base_url=url, demo_mode=demo_mode)

    def get_job(self, job_id):
        return {"id": job_id, "status": "completed", "base_url": "https://demo.example/"}

    def get_report(self, job_id):
        return self.report

    def get_pages(self, job_id):
        return PAGES_PAYLOAD


def test_run_analysis_yields_report_before_first_page_enrichment(monkeypatch):
    """First completed UI yield must happen before the enrichment POST starts."""
    events: list[str] = []
    report = _mismatch_report()

    async def fake_fetch(client, *, job_id, page_id, content_draft=True):
        events.append("enrichment_started")
        await asyncio.sleep(0)
        events.append("enrichment_finished")
        return EnrichmentEntry(
            status=EnrichmentStatus.SUCCESS,
            payload={
                "page_intelligence": {
                    "url": "https://demo.example/",
                    "title": "ENRICHED-HOME",
                    "heading_outline": ["Enriched"],
                    "answer_blocks": [],
                    "word_count": 12,
                },
                "optimization_briefs": [
                    {
                        "page_url": "https://demo.example/",
                        "action": "add_entity_markup",
                        "executive_summary": "enriched brief",
                    }
                ],
                "content_drafts": [
                    {
                        "page_url": "https://demo.example/",
                        "body_markdown": "enriched draft",
                        "generator": "deterministic_skeleton",
                    }
                ],
            },
        )

    monkeypatch.setattr("app._client", lambda: _ImmediateJob(report))
    monkeypatch.setattr("app.fetch_content_optimization", fake_fetch)

    completed = []
    for out in run_analysis(
        "https://demo.example/",
        "Single page URL",
        True,
        True,
        AnalysisState(),
    ):
        if "## Analysis overview" not in str(out[3]):
            continue
        completed.append(out)
        if "Additional optimization analysis loading" in str(out[8]):
            events.append("report_yield")
        elif "ENRICHED-HOME" in str(out[7]):
            events.append("enriched_yield")

    assert events == [
        "report_yield",
        "enrichment_started",
        "enrichment_finished",
        "enriched_yield",
    ]
    assert len(completed) == 2
    assert "CURRENT" in completed[0][7]
    assert "ENRICHED-HOME" not in completed[0][7]
    assert "ENRICHED-HOME" in completed[-1][7]
    assert completed[-1][0].report is not None


def test_run_analysis_failed_enrichment_still_shows_report(monkeypatch):
    calls = {"n": 0}

    async def fake_fetch(client, *, job_id, page_id, content_draft=True):
        calls["n"] += 1
        return EnrichmentEntry(
            status=EnrichmentStatus.ERROR,
            error_message="Optimization analysis is not available for this page (not found).",
        )

    monkeypatch.setattr("app._client", lambda: _ImmediateJob(_mismatch_report()))
    monkeypatch.setattr("app.fetch_content_optimization", fake_fetch)
    outputs = list(
        run_analysis(
            "https://demo.example/",
            "Single page URL",
            True,
            True,
            AnalysisState(),
        )
    )
    completed = _completed_yields(outputs)
    assert len(completed) >= 2
    assert "## Analysis overview" in completed[0][3]
    assert "loading" in completed[0][8].lower()
    final = completed[-1]
    assert final[0].report is not None
    assert "not found" in final[8].lower() or "Could not load" in final[8]
    assert "CURRENT" in final[7]
    cached = final[0].enrichment_cache.get("job-1", "p1")
    assert cached is not None
    assert cached.status == EnrichmentStatus.ERROR
    assert calls["n"] == 1


@pytest.mark.asyncio
async def test_inflight_reselect_single_post(monkeypatch):
    state = AnalysisState(
        job_id="job-demo-1",
        report=_mismatch_report(),
        pages=PAGES_PAYLOAD,
    )
    started = asyncio.Event()
    release = asyncio.Event()
    calls = {"n": 0}

    async def fake_fetch(client, *, job_id, page_id, content_draft=True):
        calls["n"] += 1
        started.set()
        await release.wait()
        return EnrichmentEntry(status=EnrichmentStatus.SUCCESS, payload=OPT_PAYLOAD_ABOUT)

    monkeypatch.setattr("app.fetch_content_optimization", fake_fetch)
    url = "https://demo.example/about"
    gen1 = on_select_page(url, state)
    first = await gen1.__anext__()
    assert "loading" in first[3].lower()
    assert state.enrichment_cache.get("job-demo-1", "p2").status == EnrichmentStatus.LOADING

    async def finish(gen):
        outs = []
        try:
            while True:
                outs.append(await gen.__anext__())
        except StopAsyncIteration:
            return outs

    owner = asyncio.create_task(finish(gen1))
    await asyncio.wait_for(started.wait(), timeout=2)
    gen2 = on_select_page(url, state)
    stage_a = await gen2.__anext__()
    assert "loading" in stage_a[3].lower()
    assert calls["n"] == 1
    waiter = asyncio.create_task(finish(gen2))
    release.set()
    late, final = await asyncio.gather(owner, waiter)
    assert calls["n"] == 1
    assert late and final
    assert "About" in late[-1][2]
    assert "About" in final[-1][2]
    cached = state.enrichment_cache.get("job-demo-1", "p2")
    assert cached is not None and cached.status == EnrichmentStatus.SUCCESS
    assert state.selected_page_url == url


@pytest.mark.asyncio
async def test_close_during_stage_a_clears_only_owner_loading(monkeypatch):
    started = asyncio.Event()

    async def fake_fetch(client, *, job_id, page_id, content_draft=True):
        started.set()
        await asyncio.Event().wait()
        return EnrichmentEntry(status=EnrichmentStatus.SUCCESS, payload=OPT_PAYLOAD_ABOUT)

    monkeypatch.setattr("app.fetch_content_optimization", fake_fetch)
    state = AnalysisState(
        job_id="job-demo-1",
        report=_mismatch_report(),
        pages=PAGES_PAYLOAD,
    )
    gen = on_select_page("https://demo.example/about", state)
    await gen.__anext__()
    loading = state.enrichment_cache.get("job-demo-1", "p2")
    assert loading is not None and loading.status == EnrichmentStatus.LOADING
    token = loading.owner_token
    await gen.aclose()
    assert state.enrichment_cache.get("job-demo-1", "p2") is None
    assert not started.is_set()
    role, new_token = state.enrichment_cache.claim("job-demo-1", "p2")
    assert role == "owner"
    assert state.enrichment_cache.pop_if_loading("job-demo-1", "p2", token) is False
    assert state.enrichment_cache.get("job-demo-1", "p2").status == EnrichmentStatus.LOADING
    assert new_token != token


def _about_state() -> AnalysisState:
    return AnalysisState(
        job_id="job-demo-1",
        report=_mismatch_report(),
        pages=PAGES_PAYLOAD,
    )


@pytest.mark.asyncio
async def test_concurrent_handlers_one_post_same_terminal(monkeypatch):
    """Two handlers start together, before either finishes claim's fetch."""
    state = _about_state()
    calls = {"n": 0}
    release = asyncio.Event()
    started = asyncio.Event()

    async def fake_fetch(client, *, job_id, page_id, content_draft=True):
        calls["n"] += 1
        started.set()
        await release.wait()
        return EnrichmentEntry(status=EnrichmentStatus.SUCCESS, payload=OPT_PAYLOAD_ABOUT)

    monkeypatch.setattr("app.fetch_content_optimization", fake_fetch)
    url = "https://demo.example/about"

    async def drain():
        outs = []
        async for out in on_select_page(url, state):
            outs.append(out)
        return outs

    first = asyncio.create_task(drain())
    second = asyncio.create_task(drain())
    await asyncio.wait_for(started.wait(), timeout=2)
    await asyncio.sleep(0.05)
    assert calls["n"] == 1
    loading = state.enrichment_cache.get("job-demo-1", "p2")
    assert loading is not None and loading.status == EnrichmentStatus.LOADING
    foreign = (loading.owner_token or 0) + 99
    assert state.enrichment_cache.pop_if_loading("job-demo-1", "p2", foreign) is False
    assert state.enrichment_cache.get("job-demo-1", "p2").status == EnrichmentStatus.LOADING
    release.set()
    left, right = await asyncio.gather(first, second)
    assert calls["n"] == 1
    assert "About AcmeFlow" in left[-1][2]
    assert "About AcmeFlow" in right[-1][2]
    assert left[-1][2] == right[-1][2]
    cached = state.enrichment_cache.get("job-demo-1", "p2")
    assert cached is not None and cached.status == EnrichmentStatus.SUCCESS


@pytest.mark.asyncio
async def test_cache_lifecycle_success_error_and_no_retry(monkeypatch):
    state = _about_state()
    calls = {"n": 0}
    mode = {"err": False}
    active = {"state": state}

    async def fake_fetch(client, *, job_id, page_id, content_draft=True):
        calls["n"] += 1
        current = active["state"].enrichment_cache.get(job_id, page_id)
        assert current is not None and current.status == EnrichmentStatus.LOADING
        if mode["err"]:
            return EnrichmentEntry(
                status=EnrichmentStatus.ERROR,
                error_message="Optimization analysis is temporarily unavailable. Page signals above remain valid.",
            )
        return EnrichmentEntry(status=EnrichmentStatus.SUCCESS, payload=OPT_PAYLOAD_ABOUT)

    monkeypatch.setattr("app.fetch_content_optimization", fake_fetch)

    async def drain(url, target):
        outs = []
        async for out in on_select_page(url, target):
            outs.append(out)
        return outs

    url = "https://demo.example/about"
    ok = await drain(url, state)
    assert calls["n"] == 1
    assert state.enrichment_cache.get("job-demo-1", "p2").status == EnrichmentStatus.SUCCESS
    assert "About AcmeFlow" in ok[-1][2]
    await drain(url, state)
    assert calls["n"] == 1

    mode["err"] = True
    err_state = _about_state()
    active["state"] = err_state
    bad = await drain(url, err_state)
    assert calls["n"] == 2
    assert err_state.enrichment_cache.get("job-demo-1", "p2").status == EnrichmentStatus.ERROR
    assert "CURRENT" in bad[-1][2]
    assert "unavailable" in bad[-1][3].lower() or "Could not load" in bad[-1][3]
    await drain(url, err_state)
    assert calls["n"] == 2

    other = AnalysisState(job_id="job-demo-1", report=_mismatch_report(), pages=PAGES_PAYLOAD)
    assert other.enrichment_cache.get("job-demo-1", "p2") is None
    fresh = AnalysisState(job_id="job-other", report=state.report, pages=PAGES_PAYLOAD)
    assert fresh.enrichment_cache.get("job-demo-1", "p2") is None


def test_new_analysis_does_not_reuse_prior_job_cache(monkeypatch):
    monkeypatch.setattr("app._client", lambda: _ImmediateJob(SAMPLE_REPORT))
    prior = AnalysisState(job_id="old-job", report=SAMPLE_REPORT, pages=PAGES_PAYLOAD)
    prior.enrichment_cache.set(
        "old-job",
        "p2",
        EnrichmentEntry(status=EnrichmentStatus.SUCCESS, payload=OPT_PAYLOAD_ABOUT),
    )
    outs = list(
        run_analysis("https://demo.example/", "Single page URL", True, True, prior)
    )
    state = outs[-1][0]
    assert state.job_id == "job-1"
    assert state.enrichment_cache.get("old-job", "p2") is None


@pytest.mark.asyncio
async def test_enrichment_500_timeout_and_network_keep_current(monkeypatch):
    def client_for(handler):
        return AeoApiClient(
            base_url="http://test",
            api_key="k",
            async_transport=httpx.MockTransport(handler),
        )

    async def run(handler):
        monkeypatch.setattr("app._client", lambda: client_for(handler))
        state = _about_state()
        outs = []
        async for out in on_select_page("https://demo.example/about", state):
            outs.append(out)
        return state, outs[-1]

    state, final = await run(lambda request: httpx.Response(500, json={"detail": "SECRET_DB_PASSWORD"}))
    assert state.report is not None
    assert "CURRENT" in final[2]
    blob = " ".join(str(part) for part in final)
    assert "SECRET_DB_PASSWORD" not in blob
    assert "unavailable" in final[3].lower()
    assert state.enrichment_cache.get("job-demo-1", "p2").status == EnrichmentStatus.ERROR

    def timeout_handler(request):
        raise httpx.ReadTimeout("slow")

    state, final = await run(timeout_handler)
    assert "CURRENT" in final[2]
    assert "timed out" in final[3].lower()
    assert "ReadTimeout" not in " ".join(str(part) for part in final)

    def down(request):
        raise httpx.ConnectError("connection refused")

    state, final = await run(down)
    assert "CURRENT" in final[2]
    assert "could not reach" in final[3].lower()
    assert state.report["page_intelligence"]["title"] == "AcmeFlow — Demo"
