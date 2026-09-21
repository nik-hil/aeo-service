"""Integration-style tests for Gradio app helpers (demo fixtures / mocks)."""

from __future__ import annotations

import httpx
import pytest

from app import (
    STAGE_LABELS,
    _validate_url,
    build_app,
    clear_state,
    detail_panels,
    gr_update_status,
    on_select_page,
    run_analysis,
)
from components.kpi_cards import kpi_cards_html
from fixture_report import PAGES_PAYLOAD, SAMPLE_REPORT
from glossary import GUIDE_MARKDOWN, info_text
from services.adapters import AnalysisState, adapt_overview
from services.api_client import AeoApiClient, AeoApiError


def test_validate_url():
    assert _validate_url("") is not None
    assert _validate_url("ftp://x") is not None
    assert _validate_url("https://ok.example/") is None


def test_status_html_escapes():
    html = gr_update_status('<script>x</script>', kind="err")
    assert "<script>" not in html
    assert "aeo-status-err" in html


def test_guide_and_info_icons_copy():
    assert "How to read" in GUIDE_MARKDOWN
    assert "AEO Health" in info_text("aeo_health")
    assert "Entity" in info_text("entity_score")
    assert "ranking" in info_text("aeo_health").lower() or "readiness" in info_text("aeo_health").lower()


def test_detail_panels_tabs_content():
    before, recs, brief_draft, evidence = detail_panels(SAMPLE_REPORT, "https://demo.example/")
    assert "CURRENT" in before or "observed" in before.lower()
    assert "Recommendations" in recs or "answer-first" in recs.lower()
    assert "Content gaps" in brief_draft
    assert "brief" in brief_draft.lower() or "RECOMMENDED" in brief_draft
    assert "skeleton" in brief_draft.lower() or "Draft" in brief_draft
    assert "```markdown" in brief_draft
    assert "Evidence" in evidence
    assert "Optimized Page" not in brief_draft


@pytest.mark.asyncio
async def test_page_select_updates_detail():
    state = AnalysisState(
        job_id="job-demo-1",
        report=SAMPLE_REPORT,
        pages=PAGES_PAYLOAD,
        selected_page_url="https://demo.example/",
    )
    outs = []
    async for o in on_select_page("https://demo.example/about", state):
        outs.append(o)
    assert outs
    assert state.selected_page_url == "https://demo.example/about"
    assert outs[-1][2]  # before
    assert outs[-1][4]  # brief
    assert outs[-1][5]  # evidence


def test_clear_state_resets():
    st = AnalysisState(job_id="1", report={"a": 1}, opportunities=[{"x": 1}])
    st = clear_state(st)
    assert st.report is None
    assert st.opportunities == []


def test_stage_labels_cover_pipeline():
    for key in ("crawling", "scoring", "experimenting", "completed", "failed"):
        assert key in STAGE_LABELS


def test_build_app_smoke():
    demo = build_app()
    assert demo is not None


def test_kpi_cards_html():
    vm = adapt_overview(SAMPLE_REPORT, mode="single", opportunity_count=3)
    html = kpi_cards_html(vm)
    assert "aeo-kpi-card" in html
    assert "AEO Health" in html
    assert "ⓘ" in html
    assert "<script>" not in html


def test_api_client_with_mock_transport():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/health":
            return httpx.Response(200, json={"status": "ok"})
        if request.url.path == "/api/v1/jobs" and request.method == "POST":
            return httpx.Response(
                202,
                json={
                    "id": "job-1",
                    "base_url": "https://demo.example/",
                    "status": "pending",
                    "demo_mode": True,
                    "created_at": "t",
                    "links": {"self": "s", "report": "r", "pages": "p"},
                },
            )
        if request.url.path == "/api/v1/jobs/job-1":
            return httpx.Response(
                200,
                json={
                    "id": "job-1",
                    "base_url": "https://demo.example/",
                    "status": "completed",
                    "demo_mode": True,
                    "created_at": "t",
                    "updated_at": "t",
                    "completed_at": "t",
                },
            )
        if request.url.path.endswith("/report"):
            return httpx.Response(200, json=SAMPLE_REPORT)
        if request.url.path.endswith("/pages"):
            return httpx.Response(200, json=PAGES_PAYLOAD)
        return httpx.Response(404, json={"detail": "missing"})

    transport = httpx.MockTransport(handler)
    client = AeoApiClient(base_url="http://test", api_key="k", transport=transport)
    assert client.health()["status"] == "ok"
    job = client.create_job("https://demo.example/", demo_mode=True, options={"provider": "demo"})
    assert job.id == "job-1"
    assert client.get_job("job-1")["status"] == "completed"
    assert client.get_report("job-1")["job_id"] == "job-demo-1"
    assert client.get_pages("job-1")["count"] == 2


def test_run_analysis_single_and_multi_with_mocks(monkeypatch):
    calls = {"n": 0}

    class FakeClient:
        def create_job(self, url, *, demo_mode=False, options=None):
            from services.api_client import JobRef

            return JobRef(id="job-1", status="pending", base_url=url, demo_mode=demo_mode)

        def get_job(self, job_id):
            calls["n"] += 1
            return {
                "id": job_id,
                "status": "completed" if calls["n"] > 1 else "crawling",
                "base_url": "https://demo.example/",
                "demo_mode": True,
            }

        def get_report(self, job_id):
            return SAMPLE_REPORT

        def get_pages(self, job_id):
            return PAGES_PAYLOAD

    monkeypatch.setattr("app._client", lambda: FakeClient())

    outputs = list(
        run_analysis("https://demo.example/", "Single page URL", True, True, AnalysisState())
    )
    final = outputs[-1]
    assert final[3]  # overview markdown
    assert "AEO Health" in final[3]
    assert "aeo-kpi" in final[2]
    assert final[0].report is not None

    calls["n"] = 0
    outputs = list(
        run_analysis(
            "https://demo.example/",
            "Multi-page crawl seed (same-host from seed)",
            True,
            True,
            AnalysisState(),
        )
    )
    assert outputs[-1][5]  # page table non-empty in multi
    assert len(outputs[-1][4]) >= 1  # opportunities


def test_run_analysis_clears_on_failure(monkeypatch):
    class FakeClient:
        def create_job(self, *a, **k):
            from services.api_client import JobRef

            return JobRef(id="job-x", status="pending", base_url="https://demo.example/", demo_mode=True)

        def get_job(self, job_id):
            return {"id": job_id, "status": "failed", "error_message": "boom"}

    monkeypatch.setattr("app._client", lambda: FakeClient())
    prior = AnalysisState(job_id="old", report=SAMPLE_REPORT)
    outputs = list(run_analysis("https://demo.example/", "Single page URL", True, True, prior))
    final_state = outputs[-1][0]
    assert final_state.report is None
    assert "failed" in outputs[-1][1].lower() or "boom" in outputs[-1][1].lower()


def test_run_analysis_empty_url_clears():
    prior = AnalysisState(job_id="old", report=SAMPLE_REPORT)
    outputs = list(run_analysis("", "Single page URL", False, False, prior))
    assert outputs[-1][0].report is None
    assert "Enter a URL" in outputs[-1][1] or "URL" in outputs[-1][1]


def test_api_error_shape():
    err = AeoApiError("nope", status_code=404)
    assert err.status_code == 404


def test_mode_transition_clears_via_new_analysis(monkeypatch):
    """Single↔multi: new analysis clears prior enrichment cache / selection."""

    class FakeClient:
        def create_job(self, *a, **k):
            from services.api_client import JobRef

            return JobRef(id="job-2", status="pending", base_url="https://demo.example/", demo_mode=True)

        def get_job(self, job_id):
            return {"id": job_id, "status": "completed"}

        def get_report(self, job_id):
            return SAMPLE_REPORT

        def get_pages(self, job_id):
            return PAGES_PAYLOAD

    monkeypatch.setattr("app._client", lambda: FakeClient())
    prior = AnalysisState(job_id="old", report=SAMPLE_REPORT, mode="single")
    prior.enrichment_cache.set(
        "old", "p2", __import__("services.enrichment", fromlist=["EnrichmentEntry"]).EnrichmentEntry(
            status=__import__("services.enrichment", fromlist=["EnrichmentStatus"]).EnrichmentStatus.SUCCESS,
            payload={"x": 1},
        )
    )
    outs = list(
        run_analysis(
            "https://demo.example/",
            "Multi-page crawl seed (same-host from seed)",
            True,
            True,
            prior,
        )
    )
    st = outs[-1][0]
    assert st.mode == "multi"
    assert st.enrichment_cache.get("old", "p2") is None
