"""Workstream A regressions — P1-1, P1-2, P1-4, P1-5, P1-6, P1-8 (main after P1-3).

No live DO. Paid draft path stays fail-closed without outbound HTTP.
"""

from __future__ import annotations

from pathlib import Path

from aeo_mvp.content.brief import build_optimization_brief
from aeo_mvp.content.draft import (
    DeterministicSkeletonDraftGenerator,
    PaidLLMDraftGenerator,
    build_optimized_draft,
    resolve_draft_generator,
)
from aeo_mvp.content.gaps import build_content_gap_report
from aeo_mvp.content.models import ContentGap, ContentGapReport, PageIntelligence
from aeo_mvp.content.page_intel import extract_page_intelligence
from aeo_mvp.content.pipeline import run_content_optimization
from aeo_mvp.db.models import Page, new_id
from aeo_mvp.pipeline.orchestrator import create_job_record
from tests.conftest import TEST_API_KEY

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "phase5"


def _html(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def _queryset(*rows: tuple[str, str, str, str | None]) -> dict:
    members = []
    for qid, text, intent, topic in rows:
        members.append(
            {
                "query_id": qid,
                "query": text,
                "intent": intent,
                "topic": topic,
            }
        )
    return {
        "query_set_id": "qs-a",
        "query_set_version": "query-set-v3",
        "members": members,
    }


# --- P1-1 ------------------------------------------------------------------


def test_p1_1_kind_maps_missing_answer_query_to_missing_page():
    g = ContentGap(kind="missing_answer", gap_type="query")
    assert g.gap_type == "missing_page"
    assert g.to_dict()["gap_type"] == "missing_page"


def test_p1_1_kind_maps_missing_faq_to_no_answer_block():
    g = ContentGap(kind="missing_faq", gap_type="qa_coverage")
    assert g.gap_type == "no_answer_block"
    assert g.to_dict()["gap_type"] == "no_answer_block"


def test_p1_1_sheet_native_cite_miss_preserved():
    g = ContentGap(kind="missing_answer", gap_type="cite_miss")
    assert g.gap_type == "cite_miss"


def test_p1_1_absent_coverage_emits_missing_page():
    page = extract_page_intelligence(
        _html("saas_product.html"), url="https://acme.example/"
    )
    report = build_content_gap_report(
        page,
        _queryset(
            ("abs1", "zzzz totally unrelated quantum banana taxonomy", "informational", None)
        ),
    )
    absent = [g for g in report.gaps if g.page_coverage == "absent"]
    assert absent, "expected absent coverage gap"
    assert all(g.gap_type == "missing_page" for g in absent)
    assert all(g.kind == "missing_answer" for g in absent)


# --- P1-2 ------------------------------------------------------------------


def test_p1_2_missing_faq_routes_brief_to_add_faq():
    html = """
    <html><head><title>AcmeFlow Product</title>
    <meta name="description" content="Team workflows for modern companies"/>
    </head><body><h1>AcmeFlow</h1>
    <p>AcmeFlow helps teams manage project workflows with dashboards and automation
    for enterprise customers worldwide who need reliable collaboration.</p>
    <section><h2>Features</h2>
    <p>Collaboration tools for modern teams including boards, timelines, and reporting.</p>
    </section>
    </body></html>
    """
    page = extract_page_intelligence(html, url="https://acme.example/")
    report = build_content_gap_report(page, {"members": []})
    assert any(g.kind == "missing_faq" for g in report.gaps)
    assert any(g.gap_type == "no_answer_block" for g in report.gaps)
    brief = build_optimization_brief(page, report)
    assert brief.action == "add_faq"


def test_p1_2_faq_only_report_add_faq_via_kind():
    page = extract_page_intelligence(
        _html("saas_product.html"), url="https://acme.example/"
    )
    report = ContentGapReport(
        gaps=[
            ContentGap(
                id="faq1",
                kind="missing_faq",
                gap_type="qa_coverage",
                explanation="no faq",
            )
        ]
    )
    assert report.gaps[0].gap_type == "no_answer_block"
    brief = build_optimization_brief(page, report)
    assert brief.action == "add_faq"


# --- P1-4 ------------------------------------------------------------------


def test_p1_4_draft_paid_returns_failed_not_raise():
    page = extract_page_intelligence(
        _html("saas_product.html"), url="https://acme.example/"
    )
    gaps = build_content_gap_report(page, _queryset())
    brief = build_optimization_brief(page, gaps)
    # Explicit stub still refuses live calls without raising.
    gen = PaidLLMDraftGenerator(draft_paid=True, api_key="sk-fake")
    draft = build_optimized_draft(page, brief, gaps, generator=gen)
    assert draft.status == "failed"
    assert draft.body_markdown == ""
    assert draft.faq == []
    assert draft.schema_jsonld == []
    assert draft.paid is False
    assert draft.paid_llm is False
    assert any("paid_llm_not_implemented" in w for w in draft.warnings)


def test_p1_4_api_draft_paid_with_key_returns_200_not_stub(client, monkeypatch):
    from aeo_mvp.config import get_settings
    from aeo_mvp.content.draft import DeterministicSkeletonDraftGenerator
    from tests.conftest import _install_isolated_settings

    db_url = get_settings().database_url
    _install_isolated_settings(
        monkeypatch,
        AEO_DATABASE_URL=db_url,
        AEO_API_KEY=TEST_API_KEY,
        AEO_ALLOW_UNAUTHENTICATED=False,
        AEO_ENVIRONMENT="test",
        OPENAI_API_KEY="sk-test-not-real",
    )

    r = client.post(
        "/api/v1/content-optimization",
        json={
            "html": _html("saas_product.html"),
            "url": "https://acme.example/",
            "content_draft": True,
            "draft_paid": True,
            "paid_llm_opt_in": True,
        },
    )
    assert r.status_code == 200, r.text
    data = r.json()
    draft = data["draft"]
    # Live path must NOT route through PaidLLMDraftGenerator stub.
    assert "paid_llm_stub" not in str(draft.get("method") or "")
    assert "paid_llm_not_implemented" not in " ".join(draft.get("warnings") or [])
    assert draft.get("status") in {"generated", "skipped_paid_false", "failed"}


def test_p1_4_pipeline_draft_paid_uses_skeleton_not_stub():
    from aeo_mvp.content.draft import DeterministicSkeletonDraftGenerator

    result = run_content_optimization(
        html=_html("saas_product.html"),
        url="https://acme.example/",
        generate_draft=True,
        draft_paid=True,
        llm_api_key="sk-fake",
        config={"content_draft": True, "draft_paid": True},
    )
    # Stub no longer owns draft_paid+key; grounded_synth owns paid body ops.
    assert result.draft.status == "generated"
    assert "paid_llm_stub" not in str(result.draft.method or "")
    assert isinstance(
        resolve_draft_generator(
            generate_draft=True, draft_paid=True, content_draft=True, api_key="sk-fake"
        ),
        DeterministicSkeletonDraftGenerator,
    )
    # Explicit stub provider still available for legacy tests.
    assert isinstance(
        resolve_draft_generator(
            generate_draft=True,
            draft_paid=True,
            content_draft=True,
            content_draft_provider="paid_llm_stub",
            api_key="sk-fake",
        ),
        PaidLLMDraftGenerator,
    )


# --- P1-5 ------------------------------------------------------------------


def test_p1_5_skeleton_faq_jsonld_omits_invented_answers():
    page = extract_page_intelligence(
        _html("saas_product.html"), url="https://acme.example/"
    )
    gaps = build_content_gap_report(page, {"members": []})
    brief = build_optimization_brief(page, gaps)
    # Force FAQ suggestions + FAQPage schema suggestion
    brief.faq_suggestions = [
        {"question": "What is AcmeFlow?", "answer": ""},
        {"question": "How does pricing work?", "answer": ""},
    ]
    if "FAQPage" not in brief.schema_suggestions:
        brief.schema_suggestions = list(brief.schema_suggestions) + ["FAQPage"]

    result = DeterministicSkeletonDraftGenerator().generate(page, brief)
    assert all(
        (f.get("answer") or "") == "" or "[NEEDS_SOURCE]" not in (f.get("answer") or "")
        for f in result.faq
    )
    # No invented bridging sentence
    for f in result.faq:
        ans = f.get("answer") or ""
        assert "is addressed on this page" not in ans
    faq_schemas = [s for s in result.schema_jsonld if s.get("@type") == "FAQPage"]
    assert faq_schemas == []
    assert any("faq_jsonld_omitted" in w for w in result.warnings)


def test_p1_5_source_backed_faq_may_emit_jsonld():
    page = extract_page_intelligence(
        _html("saas_product.html"), url="https://acme.example/"
    )
    gaps = build_content_gap_report(page, {"members": []})
    brief = build_optimization_brief(page, gaps)
    excerpt = "AcmeFlow is a project management platform for teams."
    brief.faq_suggestions = [{"question": "What is AcmeFlow?", "answer": excerpt}]
    brief.schema_suggestions = ["FAQPage"]
    result = DeterministicSkeletonDraftGenerator().generate(
        page, brief, source_excerpts=[excerpt]
    )
    faq_schemas = [s for s in result.schema_jsonld if s.get("@type") == "FAQPage"]
    assert len(faq_schemas) == 1
    text = faq_schemas[0]["mainEntity"][0]["acceptedAnswer"]["text"]
    assert text == excerpt
    assert "[NEEDS_SOURCE]" not in text


# --- P1-6 ------------------------------------------------------------------


def test_p1_6_page_intelligence_round_trip_preserves_additives():
    page = extract_page_intelligence(
        _html("saas_product.html"), url="https://acme.example/"
    )
    assert page.h1 or page.headings or page.topics or page.answer_units
    wire = page.to_dict()
    for key in (
        "h1",
        "headings",
        "topics",
        "faq_coverage",
        "answer_units",
        "signals",
        "body_signals",
        "answerability_signals",
        "meta_description",
    ):
        assert key in wire, f"missing additive {key}"

    restored = PageIntelligence.from_dict(wire)
    assert restored.h1 == page.h1
    assert [h.text for h in restored.headings] == [h.text for h in page.headings]
    assert restored.topics == page.topics
    assert restored.faq_coverage == page.faq_coverage
    assert len(restored.answer_units) == len(page.answer_units)
    assert len(restored.signals) == len(page.signals)
    assert restored.word_count == page.word_count

    gaps_a = build_content_gap_report(page, _queryset(("q1", "AcmeFlow", "informational", "acme")))
    gaps_b = build_content_gap_report(
        restored, _queryset(("q1", "AcmeFlow", "informational", "acme"))
    )
    assert [g.to_dict() for g in gaps_a.gaps] == [g.to_dict() for g in gaps_b.gaps]


# --- P1-8 ------------------------------------------------------------------


def test_p1_8_empty_html_string_rejected_without_opt_in(client):
    r = client.post(
        "/api/v1/content-optimization",
        json={"html": "   ", "url": "https://empty.example/"},
    )
    assert r.status_code == 400
    assert "empty" in r.json()["detail"].lower()


def test_p1_8_allow_empty_html_opt_in(client):
    r = client.post(
        "/api/v1/content-optimization",
        json={
            "html": "",
            "url": "https://empty.example/",
            "allow_empty_html": True,
        },
    )
    assert r.status_code == 200
    intel = r.json()["page_intelligence"]
    assert "empty_page_html" in (intel.get("warnings") or [])


def test_p1_8_job_page_null_html_returns_409(client):
    from aeo_mvp.db.session import get_session_factory

    session = get_session_factory()()
    try:
        job = create_job_record(
            session,
            "https://empty.example/",
            demo_mode=False,
            options={},
        )
        page = Page(
            id=new_id(),
            job_id=job.id,
            url="https://empty.example/",
            depth=0,
            html=None,
            fetch_error="robots_blocked",
            title=None,
        )
        session.add(page)
        session.commit()
        job_id, page_id = job.id, page.id
    finally:
        session.close()

    r = client.post(
        "/api/v1/content-optimization",
        json={"job_id": job_id, "page_id": page_id},
    )
    assert r.status_code == 409, r.text
    assert "empty or missing HTML" in r.json()["detail"]


def test_p1_8_job_pipeline_skips_null_html_honestly():
    from aeo_mvp.content.service import optimize_job_pages

    page = Page(
        id=new_id(),
        job_id=new_id(),
        url="https://empty.example/",
        depth=0,
        html=None,
        fetch_error="timeout",
        title=None,
    )
    out = optimize_job_pages(
        pages=[page],
        queryset={"members": []},
        site_profile=None,
        options={"content_draft": False, "draft_paid": False},
    )
    assert out["status"] == "skipped_no_html"
    assert out["page_intelligence"] is None
    assert out["content_gaps"] == []
    assert "no_eligible_page_html" in out["warnings"]
