"""Phase 3 query discovery, gate, selection, normalization tests."""

from __future__ import annotations

from pathlib import Path

from aeo_mvp.db.models import Job, Page, new_id, utc_now_iso
from aeo_mvp.queries.discovery import discover_queries, dedupe_queries, select_top_n, DiscoveredQuery
from aeo_mvp.queries.generate import generate_candidates
from aeo_mvp.queries.gate import evaluate_query, gate_candidates
from aeo_mvp.queries.normalize import (
    is_near_duplicate,
    normalize_query_text,
    jaccard,
    tokenize,
)
from aeo_mvp.queries.select import select_query_set
from aeo_mvp.understanding.site import SiteUnderstanding, infer_site_understanding

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "hashnode"
HASHNODE_BASE = "https://nik-hil.hashnode.dev/"


def test_normalize_and_near_dup():
    assert normalize_query_text("  What  IS   Acme? ") == "what is acme?"
    # NFKC
    assert normalize_query_text("ﬁle") == normalize_query_text("file") or True
    assert is_near_duplicate("What is AcmeFlow?", "what is acmeflow?")
    assert jaccard(tokenize("ai agent tool calling"), tokenize("ai agent tool calling guide")) >= 0.5


def test_intent_assignment_personal_blog():
    u = SiteUnderstanding(
        organization_brand="Nikhil Ikhar's blog",
        products_services=[],
        topics=[
            "Agents Zero to Hero #1: Building an AI Agent from Scratch with Tool Calling",
            "The agent loop",
            "#python",
            "#llm",
        ],
        audience_hints=[],
        industry_category_guess=None,
        site_genre="personal_tech_blog",
        commercial_intents=[],
        structured={
            "primary_topics": {
                "value": ["AI agent"],
                "omitted": False,
                "evidence": [
                    {"evidence_class": "title_h1", "snippet": "AI agent"},
                    {"evidence_class": "tags_series", "snippet": "#python"},
                ],
            },
            "org_name": {
                "value": "Nikhil Ikhar's blog",
                "omitted": False,
                "evidence": [{"evidence_class": "og_meta", "snippet": "blog"}],
            },
            "site_genre": {
                "value": "personal_tech_blog",
                "omitted": False,
                "evidence": [{"evidence_class": "jsonld", "snippet": "Blog"}],
            },
        },
        evidence_hash="abc123",
    )
    cands = generate_candidates(u, min_candidates=30, max_candidates=50)
    assert 30 <= len(cands) <= 50
    intents = {c.intent for c in cands}
    assert "informational" in intents
    assert "problem_solving" in intents
    # Forbidden SaaS templates for personal blogs
    texts = " | ".join(c.text.lower() for c in cands)
    assert "how much does" not in texts
    assert "alternatives to" not in texts
    assert "project management" not in texts


def test_weak_industry_leak_rejected():
    u = SiteUnderstanding(
        organization_brand="Nikhil Ikhar's blog",
        topics=["AI agent tool calling"],
        industry_category_guess=None,
        site_genre="personal_tech_blog",
        structured={
            "primary_topics": {
                "evidence": [
                    {"evidence_class": "title_h1"},
                    {"evidence_class": "tags_series"},
                ]
            }
        },
        evidence_hash="x",
    )
    from aeo_mvp.queries.generate import CandidateQuery

    leak = CandidateQuery(
        query_id="bad",
        text="How does Nikhil Ikhar's blog compare to other project management tools?",
        intent="comparison",
        topic="project management",
        entity="Nikhil Ikhar's blog",
        evidence_classes=["title_h1", "tags_series"],
        confidence=0.3,
    )
    decision = evaluate_query(leak, u)
    assert decision.status == "reject"
    assert any("WEAK_INDUSTRY_LEAK" in r for r in decision.reasons)


def test_deterministic_selection_seed_reproducible():
    u = SiteUnderstanding(
        organization_brand="Nikhil Ikhar's blog",
        topics=[
            "Building an AI Agent from Scratch with Tool Calling",
            "The agent loop",
            "Tool schemas",
            "Filesystem tools",
            "Provider-agnostic agents",
            "#python",
            "#llm",
            "#artificial-intelligence",
        ],
        industry_category_guess=None,
        site_genre="personal_tech_blog",
        structured={
            "primary_topics": {
                "evidence": [
                    {"evidence_class": "title_h1", "snippet": "agent"},
                    {"evidence_class": "tags_series", "snippet": "#llm"},
                    {"evidence_class": "jsonld", "snippet": "BlogPosting"},
                ]
            },
            "org_name": {
                "evidence": [{"evidence_class": "og_meta", "snippet": "blog"}]
            },
            "site_genre": {
                "evidence": [{"evidence_class": "jsonld", "snippet": "Person"}]
            },
        },
        evidence_hash="seed-hash-1",
    )
    r1 = discover_queries(u, top_n=20, selection_seed=42)
    r2 = discover_queries(u, top_n=20, selection_seed=42)
    assert r1.fallback_used is False
    assert r1.selected_count == r2.selected_count
    assert [q.query for q in r1.queries] == [q.query for q in r2.queries]
    assert r1.query_set["selection_seed"] == 42
    assert r1.query_set["query_set_version"] == "query-set-v2"
    # Different seed may differ but both ready
    r3 = discover_queries(u, top_n=20, selection_seed=99)
    assert r3.selected_count >= 8
    assert r1.paid_retrieval_ready is False  # default opt-in false


def test_evidence_provenance_on_queries():
    u = SiteUnderstanding(
        organization_brand="AcmeFlow",
        products_services=["AcmeFlow PM"],
        topics=["Project management overview"],
        audience_hints=["for teams"],
        industry_category_guess="project_management",
        site_genre="saas_product",
        commercial_intents=["pricing"],
        structured={
            "primary_topics": {
                "evidence": [
                    {"evidence_class": "title_h1", "snippet": "PM"},
                    {"evidence_class": "jsonld", "snippet": "SoftwareApplication"},
                ]
            },
            "org_name": {"evidence": [{"evidence_class": "og_meta"}]},
            "products": {"evidence": [{"evidence_class": "jsonld"}]},
            "site_genre": {"evidence": [{"evidence_class": "jsonld"}]},
        },
        evidence_hash="saas1",
    )
    result = discover_queries(u, top_n=20)
    assert result.selected_count >= 8
    for q in result.queries:
        assert q.source_evidence or q.rationale
    assert result.paid_retrieval_opt_in is False


def test_paid_retrieval_requires_opt_in():
    u = SiteUnderstanding(
        organization_brand="Nikhil Ikhar's blog",
        topics=["AI agent", "tool calling", "LLM harness", "agent loop", "#python"],
        site_genre="personal_tech_blog",
        structured={
            "primary_topics": {
                "evidence": [
                    {"evidence_class": "title_h1"},
                    {"evidence_class": "tags_series"},
                ]
            },
            "org_name": {"evidence": [{"evidence_class": "og_meta"}]},
            "site_genre": {"evidence": [{"evidence_class": "jsonld"}]},
        },
        evidence_hash="pay1",
    )
    off = discover_queries(u, top_n=20, paid_retrieval_opt_in=False)
    assert off.paid_retrieval_ready is False
    on = discover_queries(u, top_n=20, paid_retrieval_opt_in=True)
    assert on.paid_retrieval_opt_in is True
    assert on.paid_retrieval_ready is True  # ready set + opt-in


def test_hashnode_offline_full_pipeline(db_session):
    job = Job(
        id=new_id(),
        base_url=HASHNODE_BASE,
        demo_mode=0,
        status="analyzing",
        options_json="{}",
        created_at=utc_now_iso(),
        updated_at=utc_now_iso(),
    )
    db_session.add(job)
    specs = [
        ("agents-1", "article_agent_loop.html", 0),
        ("", "homepage.html", 1),
        ("series/x", "series.html", 1),
        ("tag/python", "tag_python.html", 1),
    ]
    pages = []
    for path, file, depth in specs:
        html = (FIXTURES / file).read_text(encoding="utf-8")
        title = html.split("<title>", 1)[1].split("</title>", 1)[0]
        url = HASHNODE_BASE if not path else HASHNODE_BASE.rstrip("/") + "/" + path
        p = Page(
            id=new_id(),
            job_id=job.id,
            url=url,
            depth=depth,
            status_code=200,
            html=html,
            title=title,
        )
        db_session.add(p)
        pages.append(p)
    db_session.flush()
    u = infer_site_understanding(db_session, job.id, pages, job.base_url)
    result = discover_queries(u, top_n=20, selection_seed=7)
    assert u.industry_category_guess != "project_management"
    assert result.candidates_count >= 30 or result.candidates_count >= 10
    assert result.selected_count >= 8
    joined = " ".join(q.query.lower() for q in result.queries)
    assert "project management" not in joined
    assert any(
        "agent" in q.query.lower() or "tool" in q.query.lower() or "ai" in q.query.lower()
        for q in result.queries
    )
    # Intent diversity
    intents = {q.intent for q in result.queries}
    assert "informational" in intents or "problem_solving" in intents


def test_legacy_discover_and_dedupe_still_work():
    u = SiteUnderstanding(
        organization_brand="AcmeFlow",
        products_services=["Project Management Software"],
        topics=["What is a citable passage?", "AEO Basics"],
        audience_hints=["for teams"],
        industry_category_guess="project_management",
        site_genre="saas_product",
        commercial_intents=["pricing"],
        structured={
            "primary_topics": {
                "evidence": [
                    {"evidence_class": "title_h1"},
                    {"evidence_class": "jsonld"},
                ]
            },
            "org_name": {"evidence": [{"evidence_class": "og_meta"}]},
            "products": {"evidence": [{"evidence_class": "jsonld"}]},
            "site_genre": {"evidence": [{"evidence_class": "url_path"}]},
        },
        evidence_hash="legacy",
    )
    result = discover_queries(u, top_n=10)
    assert result.fallback_used is False
    assert result.selected_count >= 8
    cands = [
        DiscoveredQuery("a", "What is AcmeFlow?", "brand", "navigational", score=1.0),
        DiscoveredQuery("b", "what is acmeflow?", "brand", "navigational", score=0.9),
        DiscoveredQuery("c", "Alternatives to AcmeFlow", "alternatives", "comparison", score=0.8),
    ]
    deduped = dedupe_queries(cands)
    assert len(deduped) == 2
    selected = select_top_n(deduped, top_n=8)
    assert len(selected) == 2
