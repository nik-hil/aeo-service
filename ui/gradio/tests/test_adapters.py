"""Adapter / table / before-after / empty-partial-malformed tests."""

from __future__ import annotations

from fixture_report import (
    MALFORMED_REPORT,
    PAGES_PAYLOAD,
    PARTIAL_CRAWL_REPORT,
    SAMPLE_REPORT,
)
from services.adapters import (
    AnalysisState,
    adapt_before,
    adapt_brief,
    adapt_draft,
    adapt_evidence,
    adapt_gaps,
    adapt_overview,
    adapt_pages,
    adapt_recommendations,
    draft_ui_label,
    overview_markdown,
    pages_table,
    recommendations_markdown,
)
from services.opportunities import build_opportunities, opportunities_table


def test_overview_kpis():
    vm = adapt_overview(SAMPLE_REPORT, mode="multi")
    assert vm.health.value == "87.9"
    assert vm.pages_crawled == 5
    assert vm.demo_mode is True
    assert any(c.key == "entity" for c in vm.components)
    md = overview_markdown(vm)
    assert "AEO Health" in md
    assert "Query coverage" in md or "query coverage" in md.lower() or "Query coverage" in md


def test_partial_crawl_flag():
    vm = adapt_overview(PARTIAL_CRAWL_REPORT, mode="multi")
    assert vm.crawl_partial is True
    assert "Partial crawl" in overview_markdown(vm)


def test_pages_table():
    rows = adapt_pages(PAGES_PAYLOAD)
    assert len(rows) == 2
    table = pages_table(rows)
    assert table[0][1] == "https://demo.example/"


def test_before_after_adapters():
    before = adapt_before(SAMPLE_REPORT, page_url="https://demo.example/")
    assert "AcmeFlow" in before.title
    assert "Heading outline" in before.markdown
    gaps = adapt_gaps(SAMPLE_REPORT, page_url="https://demo.example/pricing")
    assert "Content gaps" in gaps
    assert "thin_coverage" in gaps
    brief = adapt_brief(SAMPLE_REPORT, page_url="https://demo.example/")
    assert brief is not None
    assert brief.action == "expand_section"
    draft = adapt_draft(SAMPLE_REPORT, page_url="https://demo.example/")
    assert draft is not None
    assert "skeleton" in draft.label.lower()
    assert draft.content_provenance == "generated"
    assert "```markdown" in draft.body_markdown
    # homepage has no gap rows in fixture → empty-state copy
    home_gaps = adapt_gaps(SAMPLE_REPORT, page_url="https://demo.example/")
    assert "No content gaps" in home_gaps


def test_recommendations_and_evidence():
    recs = adapt_recommendations(SAMPLE_REPORT, page_url="https://demo.example/")
    assert any("answer-first" in r.title.lower() for r in recs)
    md = recommendations_markdown(recs)
    assert "Problem" in md
    ev = adapt_evidence(SAMPLE_REPORT, page_url="https://demo.example/")
    assert ev.snippets
    assert "Evidence" in ev.markdown


def test_opportunities_deterministic_order():
    opps = build_opportunities(SAMPLE_REPORT, limit=8)
    assert opps[0].kind == "recommendation"
    assert opps[0].id == "r1"  # rank 1 before rank 2
    assert opps[1].id == "r2"
    # high-severity gap on pricing not covered by rec URLs
    kinds = [o.kind for o in opps]
    assert "content_gap" in kinds
    gap = next(o for o in opps if o.kind == "content_gap")
    assert gap.page_url == "https://demo.example/pricing"
    table = opportunities_table(opps)
    assert table[0][0] == "1"


def test_empty_and_malformed():
    assert build_opportunities(None) == []
    assert build_opportunities({}) == []
    vm = adapt_overview(MALFORMED_REPORT, mode="single")
    assert vm.health.value == "—"
    recs = adapt_recommendations(MALFORMED_REPORT)
    assert len(recs) == 1
    assert adapt_pages(None) == []
    assert adapt_before({}).markdown  # still renders empty-state markdown


def test_state_clears_stale_results():
    st = AnalysisState(job_id="x", report=SAMPLE_REPORT, error="old")
    st.clear_results()
    assert st.job_id is None
    assert st.report is None
    assert st.error is None
    assert st.opportunities == []


def test_draft_ui_label_variants():
    assert "No draft" in draft_ui_label({"status": "skipped_paid_false", "body_markdown": ""})
    assert "skeleton" in draft_ui_label(
        {"status": "generated", "generator": "deterministic_skeleton", "body_markdown": "# x"}
    ).lower()
    assert "failed" in draft_ui_label({"status": "failed", "body_markdown": "x"}).lower()
