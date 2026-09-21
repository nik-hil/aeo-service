"""Stale-result clearing behavior."""

from __future__ import annotations

from app import clear_state, run_analysis
from fixture_report import SAMPLE_REPORT
from services.adapters import AnalysisState


def test_new_analysis_clears_prior_results(monkeypatch):
    class FakeClient:
        def create_job(self, *a, **k):
            raise RuntimeError("network down")

    monkeypatch.setattr("app._client", lambda: FakeClient())
    prior = AnalysisState(
        job_id="old-job",
        report=SAMPLE_REPORT,
        pages={"pages": []},
        opportunities=[{"id": "r1"}],
        selected_page_url="https://demo.example/",
    )
    outs = list(run_analysis("https://demo.example/", "Single page URL", True, True, prior))
    st = outs[-1][0]
    assert st.report is None
    assert st.job_id is None
    assert st.opportunities == []
    assert st.selected_page_url is None


def test_clear_helper():
    st = clear_state(AnalysisState(report=SAMPLE_REPORT, error="e"))
    assert st.report is None and st.error is None
