"""Phase 5 — Content Optimization tests A–X.

Fixtures only (Hashnode + SaaS + docs + ecommerce + personal blog + empty).
No live web. No paid DigitalOcean / LLM calls.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from aeo_mvp.optimization.brief import FORBIDDEN_PRACTICES, build_optimization_brief
from aeo_mvp.optimization.coverage import assess_query_coverage, coverage_level
from aeo_mvp.optimization.draft import build_optimized_draft
from aeo_mvp.optimization.gaps import build_content_gap_report
from aeo_mvp.optimization.llm import HeuristicDraftWriter, PaidLLMDraftWriter, resolve_writer
from aeo_mvp.optimization.models import (
    BRIEF_VERSION,
    DRAFT_VERSION,
    GAP_VERSION,
    PAGE_INTELLIGENCE_VERSION,
)
from aeo_mvp.optimization.page_intelligence import extract_page_intelligence
from aeo_mvp.optimization.pipeline import run_content_optimization
from aeo_mvp.queries.evidence import normalize_provenance
from aeo_mvp.scoring.health import HEALTH_FORMULA_VERSION

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
HASHNODE = FIXTURES / "hashnode"
PHASE5 = FIXTURES / "phase5"


def _html(name: str, *, root: Path = PHASE5) -> str:
    return (root / name).read_text(encoding="utf-8")


def _queryset(*items: tuple[str, str, str | None, str | None]) -> dict:
    members = []
    for qid, text, intent, topic in items:
        members.append(
            {
                "selection_rank": len(members) + 1,
                "query": {
                    "query_id": qid,
                    "text": text,
                    "intent": intent or "informational",
                    "topic": topic,
                    "entity": None,
                },
                "gate": {"accepted": True},
            }
        )
    return {
        "query_set_id": "qs_phase5_test",
        "query_set_version": "query-set-v3",
        "members": members,
        "paid_retrieval_opt_in": False,
    }


def test_a_page_intelligence_observed_facts_hashnode():
    html = _html("article_agent_loop.html", root=HASHNODE)
    page = extract_page_intelligence(
        html, url="https://nik-hil.hashnode.dev/agents-zero-to-hero-1"
    )
    assert page.schema_version == PAGE_INTELLIGENCE_VERSION
    assert page.title and "AI Agent" in page.title
    assert page.h1 and "Tool Calling" in page.h1
    assert page.meta_description
    assert any(h.text == "The agent loop" for h in page.headings)
    assert page.word_count > 20
    assert "BlogPosting" in page.structured_data.get("types", [])
    title_sig = next(s for s in page.signals if s.key == "title")
    assert title_sig.provenance == "observed"


def test_b_provenance_missing_maps_to_compatibility():
    assert normalize_provenance(None) == "compatibility"
    assert normalize_provenance("") == "compatibility"
    assert normalize_provenance("heuristic") == "derived"
    page = extract_page_intelligence(
        "<html><body><p>x</p></body></html>", url="https://ex.example/"
    )
    title_sig = next(s for s in page.signals if s.key == "title")
    assert title_sig.provenance == "compatibility"
    assert title_sig.value is None


def test_c_content_gap_categories_deterministic():
    page = extract_page_intelligence(
        _html("saas_product.html"), url="https://acme.example/"
    )
    qs = _queryset(
        ("q1", "AcmeFlow vs Jira for sprint planning", "comparison", "sprint planning"),
        ("q2", "How to automate tasks in AcmeFlow", "problem_solving", "task automation"),
        ("q3", "What is quantum knitting", "informational", "quantum knitting"),
    )
    report = build_content_gap_report(page, qs)
    assert report.schema_version == GAP_VERSION
    cats = {g.category for g in report.gaps}
    assert "query" in cats
    assert any(g.category == "query" and "q3" in g.query_ids for g in report.gaps)
    report2 = build_content_gap_report(page, qs)
    assert [g.to_dict() for g in report.gaps] == [g.to_dict() for g in report2.gaps]


def test_d_coverage_levels_separate_from_ai_visibility():
    page = extract_page_intelligence(
        _html("saas_product.html"), url="https://acme.example/"
    )
    direct, _ = coverage_level("AcmeFlow project management", page)
    assert direct == "direct"
    none, _ = coverage_level("quantum knitting patterns for cats", page)
    assert none == "none"
    rows = assess_query_coverage(
        page,
        _queryset(
            ("a", "AcmeFlow project management", "informational", "project management"),
            ("b", "quantum knitting patterns for cats", "informational", None),
        ),
    )
    by = {r.query_id: r.coverage for r in rows}
    assert by["a"] == "direct"
    assert by["b"] == "none"
    blob = json.dumps([r.to_dict() for r in rows])
    assert "ai_mention" not in blob
    assert "citation_rate" not in blob


def test_e_brief_deterministic_from_page_profile_queryset():
    page = extract_page_intelligence(
        _html("docs_site.html"), url="https://docs.example/auth"
    )
    qs = _queryset(
        ("d1", "How do WidgetSDK webhooks retry?", "problem_solving", "webhooks"),
        ("d2", "WidgetSDK rate limits explained", "informational", "rate limits"),
    )
    gaps = build_content_gap_report(page, qs)
    profile = {
        "org_name": {"value": "WidgetSDK", "omitted": False, "provenance": "heuristic"},
        "site_genre": {"value": "documentation", "omitted": False},
        "products": {"value": ["WidgetSDK"], "omitted": False},
    }
    brief = build_optimization_brief(page, gaps, site_profile=profile, queryset=qs)
    assert brief.schema_version == BRIEF_VERSION
    assert brief.proposed_title
    assert brief.proposed_h1
    assert brief.outline
    assert brief.aeo_writing_requirements
    brief2 = build_optimization_brief(page, gaps, site_profile=profile, queryset=qs)
    assert brief.to_dict() == brief2.to_dict()


def test_f_brief_forbids_keyword_stuffing_and_fake_stats():
    page = extract_page_intelligence(
        _html("personal_blog.html"), url="https://maya.example/"
    )
    gaps = build_content_gap_report(page, _queryset())
    brief = build_optimization_brief(page, gaps)
    for banned in FORBIDDEN_PRACTICES:
        assert banned in brief.forbidden_practices
    blob = json.dumps(brief.to_dict()).lower()
    assert "guaranteed #1 ranking" not in blob
    assert "studies show 97%" not in blob


def test_g_change_plan_actions_with_reasons():
    result = run_content_optimization(
        html=_html("empty_page.html"),
        url="https://empty.example/",
        queryset=_queryset(
            ("e1", "What is empty page optimization?", "informational", None)
        ),
    )
    actions = {c.action for c in result.draft.change_plan}
    assert "add" in actions
    for item in result.draft.change_plan:
        assert item.reason
        assert item.action in ("retain", "rewrite", "expand", "remove", "add")


def test_h_draft_from_source_and_brief():
    result = run_content_optimization(
        html=_html("ecommerce.html"),
        url="https://shop.example/alpine-pack",
        queryset=_queryset(
            ("s1", "Best ultralight hiking pack", "recommendation", "hiking packs"),
            ("s2", "Alpine Pack vs Summit Tent kit", "comparison", "Alpine Pack"),
        ),
        site_profile={"site_genre": {"value": "ecommerce", "omitted": False}},
    )
    draft = result.draft
    assert draft.schema_version == DRAFT_VERSION
    assert draft.title
    assert draft.body_markdown.startswith("#")
    assert draft.change_summary
    assert draft.paid_llm is False
    assert draft.llm_used is False


def test_i_unsupported_claim_warnings_present_for_placeholders():
    page = extract_page_intelligence(
        _html("saas_product.html"), url="https://acme.example/"
    )
    qs = _queryset(
        ("q9", "Does AcmeFlow increase revenue by 400 percent?", "commercial", None)
    )
    gaps = build_content_gap_report(page, qs)
    brief = build_optimization_brief(page, gaps)
    draft = build_optimized_draft(page, brief, gaps)
    assert draft.unsupported_claim_warnings
    assert any("NEEDS_SOURCE" in w or "FAQ" in w for w in draft.unsupported_claim_warnings)


def test_j_hashnode_fixture_pipeline():
    result = run_content_optimization(
        html=_html("article_agent_loop.html", root=HASHNODE),
        url="https://nik-hil.hashnode.dev/post",
        queryset=_queryset(
            (
                "h1",
                "How to build an AI agent with tool calling",
                "problem_solving",
                "AI agent",
            ),
            ("h2", "What is the agent loop?", "informational", "agent loop"),
        ),
    )
    assert result.page_intelligence.h1
    assert result.gap_report.coverage_summary
    assert result.brief.schema_version == BRIEF_VERSION
    assert result.paid_retrieval is False


def test_k_saas_fixture_pipeline():
    result = run_content_optimization(
        html=_html("saas_product.html"),
        url="https://acme.example/",
        queryset=_queryset(("k1", "AcmeFlow pricing", "commercial", "pricing")),
        site_profile={"site_genre": {"value": "saas_product", "omitted": False}},
    )
    assert "AcmeFlow" in (result.page_intelligence.title or "")


def test_l_docs_fixture_pipeline():
    result = run_content_optimization(
        html=_html("docs_site.html"),
        url="https://docs.example/",
        site_profile={"site_genre": {"value": "documentation", "omitted": False}},
    )
    assert (
        "HowTo" in result.brief.schema_suggestions
        or "Article" in result.brief.schema_suggestions
    )


def test_m_ecommerce_fixture_pipeline():
    result = run_content_optimization(
        html=_html("ecommerce.html"),
        url="https://shop.example/",
        site_profile={"site_genre": {"value": "ecommerce", "omitted": False}},
    )
    assert "Product" in result.page_intelligence.structured_data.get("types", [])


def test_n_personal_blog_fixture_pipeline():
    result = run_content_optimization(
        html=_html("personal_blog.html"),
        url="https://maya.example/",
        site_profile={"site_genre": {"value": "personal_tech_blog", "omitted": False}},
    )
    assert result.page_intelligence.word_count > 30
    assert result.draft.body_markdown


def test_o_empty_page_fixture_pipeline():
    result = run_content_optimization(
        html=_html("empty_page.html"),
        url="https://empty.example/",
    )
    assert (
        "empty_page_html" in result.page_intelligence.warnings
        or result.page_intelligence.word_count == 0
    )
    assert any(g.category == "section" for g in result.gap_report.gaps)
    assert any(g.severity in ("critical", "high") for g in result.gap_report.gaps)


def test_p_deterministic_same_inputs():
    kwargs = dict(
        html=_html("saas_product.html"),
        url="https://acme.example/",
        queryset=_queryset(
            ("p1", "AcmeFlow team workflows", "informational", "workflows")
        ),
    )
    a = run_content_optimization(**kwargs).to_dict()
    b = run_content_optimization(**kwargs).to_dict()
    assert a == b


def test_q_stable_sort_and_tie_break():
    page = extract_page_intelligence(
        _html("saas_product.html"), url="https://acme.example/"
    )
    qs = _queryset(
        ("z9", "zzz unrelated topic xyz", "informational", None),
        ("a1", "AcmeFlow project management", "informational", "project management"),
        ("m5", "partial sprint word only", "informational", "sprint"),
    )
    rows = assess_query_coverage(page, qs)
    order = {"none": 0, "mention": 1, "partial": 2, "direct": 3}
    keys = [(order[r.coverage], r.query_id) for r in rows]
    assert keys == sorted(keys)


def test_r_generated_draft_not_observed_evidence():
    result = run_content_optimization(
        html=_html("docs_site.html"),
        url="https://docs.example/",
        queryset=_queryset(
            ("r1", "How to install WidgetSDK?", "problem_solving", "SDK")
        ),
    )
    for sig in result.page_intelligence.signals:
        assert sig.provenance in ("observed", "derived", "compatibility")
    assert result.draft.writer.startswith("heuristic")
    assert result.draft.method.startswith(DRAFT_VERSION)
    for g in result.gap_report.gaps:
        for ev in g.evidence:
            assert ev.get("provenance") in ("observed", "derived", "compatibility")
            assert "body_markdown" not in ev


def test_s_llm_interface_not_called_when_paid_false():
    writer = resolve_writer(paid_llm_opt_in=False, api_key="sk-fake")
    assert isinstance(writer, HeuristicDraftWriter)
    page = extract_page_intelligence(
        _html("saas_product.html"), url="https://acme.example/"
    )
    gaps = build_content_gap_report(page, _queryset())
    brief = build_optimization_brief(page, gaps)
    with patch.object(
        PaidLLMDraftWriter, "write", side_effect=AssertionError("paid called")
    ):
        result = HeuristicDraftWriter().write(page, brief)
    assert result.paid_llm is False
    assert result.llm_used is False


def test_t_paid_writer_refuses_without_opt_in_and_never_hits_network():
    page = extract_page_intelligence(
        _html("saas_product.html"), url="https://acme.example/"
    )
    gaps = build_content_gap_report(page, _queryset())
    brief = build_optimization_brief(page, gaps)
    paid = PaidLLMDraftWriter(paid_llm_opt_in=False, api_key="sk-fake")
    out = paid.write(page, brief)
    assert out.paid_llm is False
    assert out.llm_used is False
    assert any("paid_llm_skipped" in w for w in out.warnings)

    paid2 = PaidLLMDraftWriter(paid_llm_opt_in=True, api_key="sk-fake")
    with pytest.raises(RuntimeError, match="not implemented"):
        paid2.write(page, brief)


def test_u_api_rejects_unsafe_source_url(client):
    r = client.post(
        "/api/v1/content-optimization",
        json={"source_url": "http://127.0.0.1/secret"},
    )
    assert r.status_code == 400
    assert "SSRF" in r.json()["detail"] or "Unsafe" in r.json()["detail"]


def test_v_api_accepts_html_and_queryset_offline(client):
    r = client.post(
        "/api/v1/content-optimization",
        json={
            "html": _html("personal_blog.html"),
            "url": "https://maya.example/",
            "queryset": _queryset(
                ("v1", "How to learn Rust ownership?", "informational", "ownership")
            ),
            "paid_llm_opt_in": False,
        },
    )
    assert r.status_code == 200
    data = r.json()
    assert data["page_intelligence"]["schema_version"] == PAGE_INTELLIGENCE_VERSION
    assert data["gap_report"]["schema_version"] == GAP_VERSION
    assert data["brief"]["schema_version"] == BRIEF_VERSION
    assert data["draft"]["schema_version"] == DRAFT_VERSION
    assert data["paid_llm"] is False
    assert data["paid_retrieval"] is False


def test_w_api_rejects_topic_generate_payload(client):
    r = client.post(
        "/api/v1/content-optimization",
        json={"topic": "best crm software 2026"},
    )
    assert r.status_code == 422


def test_v2_api_job_page_id_path(client):
    from aeo_mvp.db.models import Job, Page, new_id, utc_now_iso
    from aeo_mvp.db.session import get_session_factory

    job_id = new_id()
    page_id = new_id()
    factory = get_session_factory()
    session = factory()
    try:
        job = Job(
            id=job_id,
            base_url="https://acme.example/",
            demo_mode=0,
            status="completed",
            options_json="{}",
            created_at=utc_now_iso(),
            updated_at=utc_now_iso(),
        )
        page = Page(
            id=page_id,
            job_id=job_id,
            url="https://acme.example/",
            depth=0,
            status_code=200,
            html=_html("saas_product.html"),
            title="AcmeFlow",
            fetched_at=utc_now_iso(),
        )
        session.add(job)
        session.add(page)
        session.commit()
    finally:
        session.close()

    r = client.post(
        "/api/v1/content-optimization",
        json={
            "job_id": job_id,
            "page_id": page_id,
            "queryset": _queryset(
                ("j1", "AcmeFlow sprint planning", "informational", "sprint")
            ),
        },
    )
    assert r.status_code == 200
    assert "AcmeFlow" in (r.json()["page_intelligence"]["title"] or "")


def test_x_freezes_held_no_health_v1_or_query_set_v4_or_ssrf_bypass():
    assert HEALTH_FORMULA_VERSION == "health-v1"
    from aeo_mvp.queries import select as select_v1
    from aeo_mvp.queries import select_v2

    assert getattr(select_v1, "QUERY_SET_VERSION", "query-set-v2") != "query-set-v4"
    assert "query-set-v4" not in Path(select_v2.__file__).read_text(encoding="utf-8")
    from aeo_mvp.security import ssrf

    assert hasattr(ssrf, "assert_safe_public_url")
    from aeo_mvp.config import get_settings

    get_settings.cache_clear()
    assert get_settings().paid_retrieval_opt_in is False
    result = run_content_optimization(
        html="<html><body><h1>Hi</h1></body></html>", url="https://x.example/"
    )
    assert result.paid_llm is False
    assert result.paid_retrieval is False


def test_x2_no_digitalocean_import_in_optimization_package():
    opt_root = Path(__file__).resolve().parents[2] / "src" / "aeo_mvp" / "optimization"
    for path in opt_root.glob("*.py"):
        text = path.read_text(encoding="utf-8")
        assert "digitalocean" not in text.lower()
        assert "web_search" not in text
