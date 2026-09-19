"""Phase 5 brief actionability — genre gate + gap linkage + non-templaty reasons."""

from __future__ import annotations

from pathlib import Path

from aeo_mvp.content.brief import build_optimization_brief
from aeo_mvp.content.gaps import build_content_gap_report
from aeo_mvp.content.page_intel import extract_page_intelligence
from aeo_mvp.content.pipeline import run_content_optimization

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
PHASE5 = FIXTURES / "phase5"
PHASE6 = FIXTURES / "phase6"


def _qs(*items: tuple[str, str, str | None]):
    members = []
    for i, (qid, text, intent) in enumerate(items, start=1):
        members.append(
            {
                "selection_rank": i,
                "query": {
                    "query_id": qid,
                    "text": text,
                    "intent": intent or "informational",
                    "topic": text.split()[0].lower(),
                },
                "gate": {"accepted": True},
            }
        )
    return {
        "query_set_id": "qs_actionability",
        "query_set_version": "query-set-v3",
        "members": members,
        "paid_retrieval_opt_in": False,
    }


_TEMPLATY_ONLY = {
    "page_coverage was thin; write a direct answer.",
    "page_coverage was absent; write a direct answer.",
    "Improve toward answer-first summary",
    "Core body length adequate; refine per outline",
    "H1 missing",
    "Add outline section for uncovered demand",
}


def test_homepage_listing_no_article_probe_section_adds():
    html = (PHASE6 / "homepage_baseline.html").read_text(encoding="utf-8")
    page = extract_page_intelligence(html, url="https://nik-hil.hashnode.dev/")
    assert page.h1 is None or page.h1 == ""
    qs = _qs(
        ("q_perm", "How does AI Agent Permissions: Building a Safe Tool Execution Layer work?", "informational"),
        ("q_plan", "How to get started with 3. Plan mode?", "problem_solving"),
        ("q_modes", "How does The three permission modes work?", "informational"),
        ("q_brand", "Where can I find content from Nikhil Ikhar?", "navigational"),
    )
    gaps = build_content_gap_report(
        page,
        qs,
        site_profile={"site_genre": {"value": "personal_tech_blog"}},
    )
    brief = build_optimization_brief(
        page,
        gaps,
        site_profile={"site_genre": {"value": "personal_tech_blog"}},
        queryset=qs,
    )
    assert brief.scope.get("listing_index_page") is True
    section_adds = [
        w
        for w in brief.work_queue
        if w.action == "add" and w.target.startswith("section:")
    ]
    banned = ("permission", "plan mode", "three permission")
    for w in section_adds:
        low = w.target.lower()
        assert not any(b in low for b in banned), w.target
    # Prefer H1 / schema / brand-style ops
    targets = " ".join(w.target for w in brief.work_queue).lower()
    assert "h1" in targets or "schema:organization" in targets or "meta_description" in targets


def test_work_queue_and_edit_ops_have_related_gap_ids():
    html = (PHASE6 / "homepage_baseline.html").read_text(encoding="utf-8")
    result = run_content_optimization(
        html=html,
        url="https://nik-hil.hashnode.dev/",
        queryset=_qs(
            ("q1", "Where can I find content from Nikhil Ikhar?", "navigational"),
            ("q2", "How does The three permission modes work?", "informational"),
        ),
        site_profile={"site_genre": {"value": "personal_tech_blog"}},
        generate_draft=True,
    )
    gap_ids = {g.gap_id or g.id for g in result.gap_report.gaps}
    assert gap_ids
    for w in result.brief.work_queue:
        assert w.related_gap_ids, w
        assert set(w.related_gap_ids) <= gap_ids
    for e in result.brief.edit_ops:
        assert e.related_gap_ids, e
        assert set(e.related_gap_ids) <= gap_ids
    for c in result.draft.change_plan:
        assert c.related_gap_ids, c
        assert set(c.related_gap_ids) <= gap_ids


def test_reasons_not_templaty_only_include_evidence_or_query():
    html = (PHASE5 / "saas_product.html").read_text(encoding="utf-8")
    result = run_content_optimization(
        html=html,
        url="https://acme.example/product",
        queryset=_qs(
            ("q1", "AcmeFlow vs Jira for sprint planning", "comparison"),
            ("q2", "What is quantum knitting", "informational"),
        ),
        site_profile={"site_genre": {"value": "saas_product"}},
        generate_draft=False,
    )
    for w in result.brief.work_queue:
        reason = (w.reason or "").strip()
        assert reason not in _TEMPLATY_ONLY, reason
        assert (
            "evidence=" in reason
            or "query=" in reason
            or "gap_id=" in reason
            or "word_count=" in reason
            or "schema_types=" in reason
            or "current=" in reason
            or "H1 missing" in reason
            and "evidence=" in reason
        ), reason


def test_article_no_cross_article_permission_section_bleed():
    html = (PHASE6 / "article_agent1_baseline.html").read_text(encoding="utf-8")
    result = run_content_optimization(
        html=html,
        url="https://nik-hil.hashnode.dev/agents-zero-to-hero-1-building-an-ai-agent-from-scratch-with-tool-calling",
        queryset=_qs(
            ("q_tool", "How do you build an AI agent with tool calling?", "problem_solving"),
            ("q_perm", "How does The three permission modes work?", "informational"),
            ("q_plan", "How to get started with 3. Plan mode?", "problem_solving"),
        ),
        site_profile={"site_genre": {"value": "personal_tech_blog"}},
        generate_draft=False,
    )
    assert result.brief.scope.get("listing_index_page") is False
    section_adds = [
        w.target.lower()
        for w in result.brief.work_queue
        if w.action == "add" and w.target.startswith("section:")
    ]
    assert not any("permission modes" in t for t in section_adds)
    assert not any("plan mode" in t for t in section_adds)
    # Off-topic probes should route to cross_page_link (or be absent), not section farms
    for w in result.brief.work_queue:
        if w.related_query_ids and "q_perm" in w.related_query_ids:
            assert w.target == "cross_page_link" or not w.target.startswith("section:")
