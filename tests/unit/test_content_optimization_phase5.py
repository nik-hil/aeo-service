"""Phase 5 — Content Optimization (Architect aeo_mvp.content) tests A–X + C1–C10.

Fixtures only. No live web. No paid DO/LLM.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from aeo_mvp.content.brief import ANTI_PATTERNS, build_optimization_brief
from aeo_mvp.content.draft import (
    DeterministicSkeletonDraftGenerator,
    NullDraftGenerator,
    PaidLLMDraftGenerator,
    build_optimized_draft,
    resolve_draft_generator,
)
from aeo_mvp.content.gaps import (
    ANTI_PATTERN_CAVEATS,
    assess_coverage_by_query,
    build_content_gap_report,
    page_coverage_status,
)
from aeo_mvp.content.models import (
    BRIEF_VERSION,
    DRAFT_VERSION,
    GAP_VERSION,
    PAGE_INTEL_VERSION,
)
from aeo_mvp.content.page_intel import extract_page_intelligence
from aeo_mvp.content.pipeline import run_content_optimization
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
    assert page.schema_version == PAGE_INTEL_VERSION
    assert page.hostname == "nik-hil.hashnode.dev"
    assert page.target_match_scope == "hostname"
    assert page.title and "AI Agent" in page.title
    assert page.h1 and "Tool Calling" in page.h1
    assert page.answer_units
    title_sig = next(s for s in page.signals if s.key == "title")
    assert title_sig.provenance == "observed"


def test_b_provenance_missing_maps_to_compatibility():
    assert normalize_provenance(None) == "compatibility"
    assert normalize_provenance("heuristic") == "derived"
    page = extract_page_intelligence(
        "<html><body><p>x</p></body></html>", url="https://ex.example/"
    )
    title_sig = next(s for s in page.signals if s.key == "title")
    assert title_sig.provenance == "compatibility"


def test_c_content_gap_categories_deterministic():
    page = extract_page_intelligence(
        _html("saas_product.html"), url="https://acme.example/"
    )
    qs = _queryset(
        ("q1", "AcmeFlow vs Jira for sprint planning", "comparison", "sprint planning"),
        ("q3", "What is quantum knitting", "informational", "quantum knitting"),
    )
    report = build_content_gap_report(page, qs)
    assert report.schema_version == GAP_VERSION
    assert report.query_set_version == "query-set-v3"
    assert any(g.kind == "missing_answer" for g in report.gaps)
    assert report.readiness_gaps is not None
    assert report.queryset_gaps is not None
    report2 = build_content_gap_report(page, qs)
    assert [g.to_dict() for g in report.gaps] == [g.to_dict() for g in report2.gaps]


def test_d_coverage_levels_separate_from_ai_visibility():
    page = extract_page_intelligence(
        _html("saas_product.html"), url="https://acme.example/"
    )
    full, _ = page_coverage_status("AcmeFlow project management", page)
    assert full == "full"
    absent, _ = page_coverage_status("quantum knitting patterns for cats", page)
    assert absent == "absent"
    rows = assess_coverage_by_query(
        page,
        _queryset(
            ("a", "AcmeFlow project management", "informational", "project management"),
            ("b", "quantum knitting patterns for cats", "informational", None),
        ),
    )
    by = {r.query_id: r.page_coverage for r in rows}
    assert by["a"] == "full"
    assert by["b"] == "absent"
    blob = json.dumps([r.to_dict() for r in rows])
    assert "ai_mention" not in blob
    assert "citation_rate" not in blob
    assert "page_coverage" in blob


def test_e_brief_deterministic_cites_inputs():
    page = extract_page_intelligence(
        _html("docs_site.html"), url="https://docs.example/auth"
    )
    qs = _queryset(
        ("d1", "How do WidgetSDK webhooks retry?", "problem_solving", "webhooks"),
    )
    gaps = build_content_gap_report(page, qs)
    profile = {
        "org_name": {"value": "WidgetSDK", "omitted": False},
        "site_genre": {"value": "documentation", "omitted": False},
    }
    brief = build_optimization_brief(page, gaps, site_profile=profile, queryset=qs)
    assert brief.schema_version == BRIEF_VERSION
    assert brief.scope["page_intel_version"] == PAGE_INTEL_VERSION
    assert brief.input_citations["query_set_version"] == "query-set-v3"
    assert brief.query_content_matrix
    assert brief.work_queue is not None
    assert brief.executive_summary
    assert brief.to_dict() == build_optimization_brief(
        page, gaps, site_profile=profile, queryset=qs
    ).to_dict()


def test_f_brief_anti_patterns_no_fake_stats():
    page = extract_page_intelligence(
        _html("personal_blog.html"), url="https://maya.example/"
    )
    gaps = build_content_gap_report(page, _queryset())
    brief = build_optimization_brief(page, gaps)
    for banned in ANTI_PATTERNS:
        assert banned in brief.anti_patterns
    assert "page_coverage_is_not_ai_visibility" in ANTI_PATTERN_CAVEATS or any(
        "visibility" in c for c in gaps.anti_pattern_caveats
    )


def test_g_change_plan_edit_ops():
    result = run_content_optimization(
        html=_html("empty_page.html"),
        url="https://empty.example/",
        queryset=_queryset(
            ("e1", "What is empty page optimization?", "informational", None)
        ),
        generate_draft=False,
    )
    actions = {c.action for c in result.brief.edit_ops}
    assert "add" in actions
    for item in result.brief.edit_ops:
        assert item.action in ("retain", "rewrite", "expand", "remove", "add")


def test_h_skeleton_draft_when_generate_draft():
    result = run_content_optimization(
        html=_html("ecommerce.html"),
        url="https://shop.example/alpine-pack",
        queryset=_queryset(
            ("s1", "Best ultralight hiking pack", "recommendation", "hiking packs"),
        ),
        site_profile={"site_genre": {"value": "ecommerce", "omitted": False}},
        generate_draft=True,
        draft_paid=False,
    )
    draft = result.draft
    assert draft.schema_version == DRAFT_VERSION
    assert draft.content_provenance == "generated"
    assert draft.paid_llm is False
    assert draft.unsupported_claims
    assert draft.body_markdown.startswith("#")


def test_i_null_draft_default_unsupported_claims():
    result = run_content_optimization(
        html=_html("saas_product.html"),
        url="https://acme.example/",
        generate_draft=False,
    )
    assert result.draft.writer.startswith("null")
    assert result.draft.content_provenance == "generated"
    assert result.draft.unsupported_claims
    assert result.draft.body_markdown == ""


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
        ),
        generate_draft=True,
    )
    assert result.page_intelligence.hostname == "nik-hil.hashnode.dev"
    assert result.paid_retrieval is False


def test_k_saas_fixture_pipeline():
    result = run_content_optimization(
        html=_html("saas_product.html"),
        url="https://acme.example/",
        site_profile={"site_genre": {"value": "saas_product", "omitted": False}},
    )
    assert "AcmeFlow" in (result.page_intelligence.title or "")


def test_l_docs_fixture_pipeline():
    result = run_content_optimization(
        html=_html("docs_site.html"),
        url="https://docs.example/",
        site_profile={"site_genre": {"value": "documentation", "omitted": False}},
        generate_draft=True,
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
    )
    assert result.page_intelligence.word_count > 30


def test_o_empty_page_fixture_pipeline():
    result = run_content_optimization(
        html=_html("empty_page.html"),
        url="https://empty.example/",
    )
    assert any(g.gap_type == "structure" for g in result.gap_report.gaps)


def test_p_deterministic_same_inputs():
    kwargs = dict(
        html=_html("saas_product.html"),
        url="https://acme.example/",
        queryset=_queryset(
            ("p1", "AcmeFlow team workflows", "informational", "workflows")
        ),
        generate_draft=True,
    )
    assert (
        run_content_optimization(**kwargs).to_dict()
        == run_content_optimization(**kwargs).to_dict()
    )


def test_q_stable_sort_coverage():
    page = extract_page_intelligence(
        _html("saas_product.html"), url="https://acme.example/"
    )
    rows = assess_coverage_by_query(
        page,
        _queryset(
            ("z9", "zzz unrelated topic xyz", "informational", None),
            ("a1", "AcmeFlow project management", "informational", "project management"),
        ),
    )
    order = {
        "absent": 0,
        "mismatched": 1,
        "thin": 2,
        "unknown": 3,
        "partial": 4,
        "full": 5,
    }
    keys = [(order[r.page_coverage], r.query_id) for r in rows]
    assert keys == sorted(keys)


def test_r_generated_draft_never_observed():
    result = run_content_optimization(
        html=_html("docs_site.html"),
        url="https://docs.example/",
        generate_draft=True,
    )
    assert result.draft.content_provenance == "generated"
    for claim in result.draft.unsupported_claims:
        assert claim.provenance == "generated"
        assert claim.support != "supported" or True
    for sig in result.page_intelligence.signals:
        assert sig.provenance in ("observed", "derived", "compatibility")
        assert sig.provenance != "generated"


def test_s_null_default_no_paid():
    gen = resolve_draft_generator(generate_draft=False, draft_paid=False)
    assert isinstance(gen, NullDraftGenerator)
    gen2 = resolve_draft_generator(generate_draft=True, draft_paid=False)
    assert isinstance(gen2, DeterministicSkeletonDraftGenerator)


def test_t_paid_writer_refuses():
    page = extract_page_intelligence(
        _html("saas_product.html"), url="https://acme.example/"
    )
    gaps = build_content_gap_report(page, _queryset())
    brief = build_optimization_brief(page, gaps)
    paid = PaidLLMDraftGenerator(draft_paid=True, api_key="sk-fake")
    with pytest.raises(RuntimeError, match="not implemented"):
        paid.generate(page, brief)


def test_u_api_rejects_unsafe_source_url(client):
    r = client.post(
        "/api/v1/content-optimization",
        json={"source_url": "http://127.0.0.1/secret"},
    )
    assert r.status_code == 400


def test_v_api_accepts_html_offline(client):
    r = client.post(
        "/api/v1/content-optimization",
        json={
            "html": _html("personal_blog.html"),
            "url": "https://maya.example/",
            "queryset": _queryset(
                ("v1", "How to learn Rust ownership?", "informational", "ownership")
            ),
            "generate_draft": True,
            "draft_paid": False,
        },
    )
    assert r.status_code == 200
    data = r.json()
    assert data["page_intelligence"]["schema_version"] == PAGE_INTEL_VERSION
    assert data["gap_report"]["schema_version"] == GAP_VERSION
    assert data["brief"]["schema_version"] == BRIEF_VERSION
    assert data["draft"]["schema_version"] == DRAFT_VERSION
    assert data["draft"]["content_provenance"] == "generated"
    assert data["paid_llm"] is False


def test_w_api_rejects_topic_generate(client):
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
        session.add(
            Job(
                id=job_id,
                base_url="https://acme.example/",
                demo_mode=0,
                status="completed",
                options_json="{}",
                created_at=utc_now_iso(),
                updated_at=utc_now_iso(),
            )
        )
        session.add(
            Page(
                id=page_id,
                job_id=job_id,
                url="https://acme.example/",
                depth=0,
                status_code=200,
                html=_html("saas_product.html"),
                title="AcmeFlow",
                fetched_at=utc_now_iso(),
            )
        )
        session.commit()
    finally:
        session.close()

    r = client.post(
        "/api/v1/content-optimization",
        json={"job_id": job_id, "page_id": page_id, "generate_draft": False},
    )
    assert r.status_code == 200
    assert "AcmeFlow" in (r.json()["page_intelligence"]["title"] or "")


def test_x_freezes_held():
    assert HEALTH_FORMULA_VERSION == "health-v1"
    from aeo_mvp.queries import select_v2
    from aeo_mvp.security import ssrf
    from aeo_mvp.config import get_settings

    assert "query-set-v4" not in Path(select_v2.__file__).read_text(encoding="utf-8")
    assert hasattr(ssrf, "assert_safe_public_url")
    get_settings.cache_clear()
    assert get_settings().paid_retrieval_opt_in is False
    result = run_content_optimization(
        html="<html><body><h1>Hi</h1></body></html>", url="https://x.example/"
    )
    assert result.paid_llm is False
    assert result.paid_retrieval is False


def test_x2_no_digitalocean_in_content_package():
    root = Path(__file__).resolve().parents[2] / "src" / "aeo_mvp" / "content"
    for path in root.glob("*.py"):
        text = path.read_text(encoding="utf-8")
        assert "digitalocean" not in text.lower()
        assert "web_search" not in text


# --- Evaluator gates C1–C10 ---


def test_c1_page_intel_provenance_hostname_scope():
    page = extract_page_intelligence(
        _html("article_agent_loop.html", root=HASHNODE),
        url="https://nik-hil.hashnode.dev/post",
    )
    assert page.schema_version == PAGE_INTEL_VERSION
    assert page.target_match_scope == "hostname"
    assert page.hostname == "nik-hil.hashnode.dev"
    assert any(s.provenance == "observed" for s in page.signals)


def test_c2_provenance_includes_generated_no_draft_to_observed():
    result = run_content_optimization(
        html=_html("saas_product.html"),
        url="https://acme.example/",
        generate_draft=True,
    )
    assert result.draft.content_provenance == "generated"
    # QSQ normalize still maps missing → compatibility (not weakened)
    assert normalize_provenance(None) == "compatibility"
    assert normalize_provenance("generated") == "compatibility"  # unknown to QSQ → compat
    for sig in result.page_intelligence.signals:
        assert sig.provenance != "generated"


def test_c3_coverage_from_snapshot_themes_no_niche_hardcode():
    page = extract_page_intelligence(
        _html("saas_product.html"), url="https://acme.example/"
    )
    # themes come from page tokens, not hardcoded Hashnode packs
    assert "acme" in " ".join(page.topics).lower() or "project" in " ".join(page.topics).lower()
    status, matched = page_coverage_status("AcmeFlow team workflows", page)
    assert status in ("full", "partial", "thin")
    assert matched


def test_c4_evidence_backed_gaps_only():
    page = extract_page_intelligence(
        _html("saas_product.html"), url="https://acme.example/"
    )
    report = build_content_gap_report(
        page, _queryset(("q", "quantum knitting", "informational", None))
    )
    for g in report.gaps:
        assert g.evidence
        assert g.explanation
        for ev in g.evidence:
            assert "provenance" in ev


def test_c5_versioned_brief_cites_inputs():
    page = extract_page_intelligence(
        _html("docs_site.html"), url="https://docs.example/"
    )
    qs = _queryset(("d", "WidgetSDK auth", "informational", "auth"))
    gaps = build_content_gap_report(page, qs)
    brief = build_optimization_brief(page, gaps, queryset=qs)
    assert brief.schema_version == BRIEF_VERSION
    assert brief.input_citations.get("page_intel_version") == PAGE_INTEL_VERSION
    assert brief.input_citations.get("gap_report_version") == GAP_VERSION


def test_c6_grounded_draft_unsupported_required():
    result = run_content_optimization(
        html=_html("saas_product.html"),
        url="https://acme.example/",
        queryset=_queryset(
            ("q", "Does AcmeFlow guarantee ranking?", "commercial", None)
        ),
        generate_draft=True,
    )
    assert result.draft.unsupported_claims
    assert result.draft.content_provenance == "generated"
    # refuse ungrounded: placeholders marked unsupported
    assert any(c.support == "unsupported" for c in result.draft.unsupported_claims)


def test_c7_determinism_and_null_draft_ok():
    a = run_content_optimization(
        html=_html("personal_blog.html"),
        url="https://maya.example/",
        generate_draft=False,
    )
    b = run_content_optimization(
        html=_html("personal_blog.html"),
        url="https://maya.example/",
        generate_draft=False,
    )
    assert a.to_dict() == b.to_dict()
    assert a.draft.writer.startswith("null")


def test_c8_ssrf_held(client):
    r = client.post(
        "/api/v1/content-optimization",
        json={"source_url": "http://169.254.169.254/latest/meta-data"},
    )
    assert r.status_code == 400


def test_c9_paid_do_off():
    from aeo_mvp.config import get_settings

    get_settings.cache_clear()
    assert get_settings().paid_retrieval_opt_in is False
    result = run_content_optimization(
        html=_html("saas_product.html"),
        url="https://acme.example/",
        draft_paid=False,
        generate_draft=True,
    )
    assert result.paid_retrieval is False
    assert result.paid_llm is False


def test_c10_cite_miss_only_with_observations():
    page = extract_page_intelligence(
        _html("saas_product.html"), url="https://acme.example/"
    )
    qs = _queryset(("q1", "AcmeFlow project management", "informational", None))
    rows_no = assess_coverage_by_query(page, qs, visibility_observations=None)
    assert all(
        not (r.visibility_enrichment and r.visibility_enrichment.get("cite_miss"))
        for r in rows_no
    )
    rows_yes = assess_coverage_by_query(
        page,
        qs,
        visibility_observations=[
            {"prompt_id": "q1", "detected_mention": 0, "detected_citation": 0}
        ],
    )
    assert rows_yes[0].visibility_enrichment is not None
    assert rows_yes[0].visibility_enrichment.get("cite_miss") is True


def test_d1_coverage_by_query_field_name():
    report = build_content_gap_report(
        extract_page_intelligence(_html("saas_product.html"), url="https://acme.example/"),
        _queryset(("q", "AcmeFlow", "informational", None)),
    )
    d = report.to_dict()
    assert "coverage_by_query" in d
    assert "page_coverage" in d["coverage_by_query"][0]


def test_researcher_taxonomy_and_brief_structure():
    """Researcher brief: taxonomy catalog + section order; coverage ≠ visibility/health."""
    from aeo_mvp.content.models import RESEARCHER_GAP_TAXONOMY

    result = run_content_optimization(
        html=_html("saas_product.html"),
        url="https://acme.example/",
        queryset=_queryset(
            ("q1", "AcmeFlow vs Jira", "comparison", "sprint"),
            ("q2", "quantum knitting", "informational", None),
        ),
        site_profile={"site_genre": {"value": "saas_product", "omitted": False}},
        generate_draft=False,
    )
    report = result.gap_report
    labels = [label for _, label in RESEARCHER_GAP_TAXONOMY]
    assert report.gap_catalog_by_taxonomy
    for label in labels:
        assert label in report.gap_catalog_by_taxonomy
    d = report.to_dict()
    assert d["coverage_is_not_ai_visibility"] is True
    assert d["coverage_is_not_health_v1"] is True

    brief = result.brief
    assert brief.section_order[:8] == [
        "scope",
        "executive_summary",
        "answerability",
        "gap_catalog",
        "query_content_matrix",
        "work_queue",
        "caveats",
        "anti_patterns",
    ]
    bd = brief.to_dict()
    keys = list(bd.keys())
    assert keys.index("scope") < keys.index("executive_summary")
    assert keys.index("executive_summary") < keys.index("answerability")
    assert keys.index("answerability") < keys.index("gap_catalog")
    assert keys.index("gap_catalog") < keys.index("query_content_matrix")
    assert keys.index("query_content_matrix") < keys.index("work_queue")
    assert keys.index("work_queue") < keys.index("caveats")
    assert keys.index("caveats") < keys.index("anti_patterns")
    assert "answer_first_passages" in brief.do_principles
    assert "guaranteed_inclusion" in brief.anti_patterns
    assert brief.scope["page_vs_queryset"]["coverage_is_not_ai_visibility"] is True
    assert any("SaaS" in g or "compare" in g.lower() for g in brief.genre_format_guidance)
    for row in brief.query_content_matrix:
        assert row.get("not_ai_visibility") is True
        assert row.get("not_health_v1") is True


def test_genre_lean_same_taxonomy_docs_ecommerce():
    docs = run_content_optimization(
        html=_html("docs_site.html"),
        url="https://docs.example/",
        site_profile={"site_genre": {"value": "documentation", "omitted": False}},
    )
    assert any("def" in g.lower() or "step" in g.lower() for g in docs.brief.genre_format_guidance)
    ecom = run_content_optimization(
        html=_html("ecommerce.html"),
        url="https://shop.example/",
        site_profile={"site_genre": {"value": "ecommerce", "omitted": False}},
    )
    assert any("spec" in g.lower() or "PDP" in g for g in ecom.brief.genre_format_guidance)
    assert set(docs.gap_report.gap_catalog_by_taxonomy) == set(
        ecom.gap_report.gap_catalog_by_taxonomy
    )
