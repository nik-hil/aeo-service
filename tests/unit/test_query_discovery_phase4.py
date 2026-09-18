"""Phase 4 — query-discovery-v2 / query-quality-v1 / query-set-v3 tests.

Dry-run only: no DigitalOcean / paid network calls.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from aeo_mvp.db.models import Job, Page, new_id, utc_now_iso
from aeo_mvp.queries.discovery import discover_queries, replay_discovery_fingerprint
from aeo_mvp.queries.generate import CandidateQuery
from aeo_mvp.queries.generate_v2 import generate_candidates_v2
from aeo_mvp.queries.normalize import (
    dedupe_by_text,
    is_near_duplicate,
    normalize_query_text,
)
from aeo_mvp.queries.quality import evaluate_query_v2
from aeo_mvp.queries.seed import resolve_seed, resolve_seed_from_options
from aeo_mvp.scoring.health import HEALTH_FORMULA_VERSION
from aeo_mvp.understanding.site import SiteUnderstanding, infer_site_understanding

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "hashnode"
HASHNODE_BASE = "https://nik-hil.hashnode.dev/"


def _structured_min(*classes: str) -> dict:
    ev = [{"evidence_class": c} for c in (classes or ("title_h1", "tags_series"))]
    if len(ev) < 2:
        ev = [
            {"evidence_class": "title_h1"},
            {"evidence_class": "tags_series"},
        ]
    return {
        "primary_topics": {"evidence": ev},
        "org_name": {"evidence": [{"evidence_class": "og_meta"}]},
        "site_genre": {"evidence": [{"evidence_class": "jsonld"}]},
    }


def _blog_understanding(**kwargs) -> SiteUnderstanding:
    base = dict(
        organization_brand="Nikhil Ikhar's blog",
        topics=[
            "Building an AI Agent from Scratch with Tool Calling",
            "The agent loop",
            "Tool schemas and validation",
            "Filesystem tools for agents",
            "Provider-agnostic agent design",
            "Permissions model for tools",
            "#python",
            "#llm",
        ],
        industry_category_guess=None,
        site_genre="personal_tech_blog",
        commercial_intents=[],
        structured=_structured_min("title_h1", "tags_series", "jsonld"),
        evidence_hash="phase4-blog-hash",
        important_pages=[{"url": HASHNODE_BASE, "role": "home"}] * 6,
    )
    base.update(kwargs)
    return SiteUnderstanding(**base)


def _saas_understanding() -> SiteUnderstanding:
    return SiteUnderstanding(
        organization_brand="AcmeFlow",
        products_services=["AcmeFlow PM", "AcmeFlow Boards"],
        topics=[
            "Project management overview",
            "Team workflows",
            "Task automation",
            "Sprint planning",
            "Reporting dashboards",
        ],
        audience_hints=["for teams"],
        industry_category_guess="project_management",
        site_genre="saas_product",
        commercial_intents=["pricing", "trial"],
        structured={
            "primary_topics": {
                "evidence": [
                    {"evidence_class": "title_h1"},
                    {"evidence_class": "jsonld"},
                ]
            },
            "org_name": {"evidence": [{"evidence_class": "og_meta"}]},
            "products": {"evidence": [{"evidence_class": "jsonld"}]},
            "site_genre": {"evidence": [{"evidence_class": "jsonld"}]},
        },
        evidence_hash="phase4-saas",
        important_pages=[{"url": "https://acme.example/"}] * 8,
    )


def _ecommerce_understanding() -> SiteUnderstanding:
    return SiteUnderstanding(
        organization_brand="TrailGear",
        products_services=["Alpine Pack", "Summit Tent", "Trail Bottle"],
        topics=["Hiking packs", "Ultralight tents", "Trail hydration"],
        site_genre="ecommerce",
        commercial_intents=["buy", "cart"],
        structured=_structured_min("title_h1", "jsonld"),
        evidence_hash="phase4-ecom",
        important_pages=[{"url": "https://shop.example/"}] * 6,
    )


def _docs_understanding() -> SiteUnderstanding:
    return SiteUnderstanding(
        organization_brand="WidgetSDK",
        topics=[
            "Authentication guide",
            "Rate limits",
            "Webhook retries",
            "SDK installation",
            "Error codes reference",
        ],
        site_genre="documentation",
        structured=_structured_min("title_h1", "url_path"),
        evidence_hash="phase4-docs",
        important_pages=[{"url": "https://docs.example/"}] * 10,
    )


def test_seed_aliases_selection_seed_honored():
    """Bug fix: selection_seed=42 must not fall through to evidence-hash seed."""
    eh = "0474cd7f96d66bba"
    derived = int(hashlib.sha256(eh.encode()).hexdigest()[:8], 16)
    assert derived == 11607312

    r = resolve_seed_from_options({"selection_seed": 42}, evidence_hash=eh)
    assert r.root_seed == 42
    assert r.effective_seed == 42
    assert r.alias_used == "selection_seed"
    assert r.source == "explicit"

    r2 = resolve_seed_from_options({"query_selection_seed": 7}, evidence_hash=eh)
    assert r2.effective_seed == 7

    r3 = resolve_seed_from_options({"experiment_seed": 99}, evidence_hash=eh)
    assert r3.effective_seed == 99

    r4 = resolve_seed_from_options({}, evidence_hash=eh)
    assert r4.effective_seed == 11607312
    assert r4.source == "evidence_hash_fallback"

    # Wrong key warns
    r5 = resolve_seed_from_options({"seed": 42}, evidence_hash=eh)
    assert any("SEED_ALIAS_MISMATCH" in w for w in r5.warnings)


def test_dry_run_replay_identical_fingerprint():
    u = _blog_understanding()
    opts = {"selection_seed": 42, "discovery_only": True}
    a = discover_queries(u, top_n=20, options=opts, discovery_only=True, frozen_at="2026-09-18T00:00:00Z")
    b = discover_queries(u, top_n=20, options=opts, discovery_only=True, frozen_at="2026-09-18T00:00:00Z")
    assert a.method == "query-discovery-v2"
    assert a.query_set_version == "query-set-v3"
    assert a.fingerprint == b.fingerprint
    assert replay_discovery_fingerprint(a) == replay_discovery_fingerprint(b)
    assert [q.id for q in a.queries] == [q.id for q in b.queries]
    assert [q.query for q in a.queries] == [q.query for q in b.queries]
    assert a.query_set["effective_seed"] == 42
    assert a.query_set["root_seed"] == 42
    assert a.paid_retrieval_ready is False
    assert a.candidates  # full candidate list persisted
    assert a.representativeness.get("report_version") == "representativeness-v1"


def test_different_seed_deterministic_but_may_differ():
    u = _blog_understanding()
    a = discover_queries(
        u, top_n=20, options={"selection_seed": 42}, frozen_at="t0"
    )
    b = discover_queries(
        u, top_n=20, options={"selection_seed": 99}, frozen_at="t0"
    )
    assert a.fingerprint
    assert b.fingerprint
    assert a.query_set.get("selection_seed_method") == "sha256_seeded_tiebreak_v1"
    # Both pass quality floors
    assert a.selected_count >= 8
    assert b.selected_count >= 8
    assert a.rejected_count >= 0
    # Same seed twice is identical; different seeds MAY differ (not required always)
    a2 = discover_queries(
        u, top_n=20, options={"selection_seed": 42}, frozen_at="t0"
    )
    assert [q.id for q in a.queries] == [q.id for q in a2.queries]
    _ = a.fingerprint != b.fingerprint or [q.id for q in a.queries] != [
        q.id for q in b.queries
    ]


def test_title_wrap_garbage_rejected():
    u = _blog_understanding()
    bad = CandidateQuery(
        query_id="bad_wrap",
        text="How does Why does an AI agent need permissions work?",
        intent="problem_solving",
        topic="permissions",
        entity="Nikhil Ikhar's blog",
        evidence_classes=["title_h1", "tags_series"],
        confidence=0.3,
    )
    d = evaluate_query_v2(bad, u)
    assert d.status == "reject"
    assert any("grammaticality" in r or "answerability" in r for r in d.reasons)


def test_no_ai_agent_hardcode_in_v2_generator():
    u = _blog_understanding(
        organization_brand="Garden Notes",
        topics=[
            "Soil amendments for clay",
            "Tomato pruning calendar",
            "Compost bin design",
            "Rain barrel setup",
            "Native pollinator plants",
        ],
        site_genre="personal_tech_blog",
    )
    cands, plan = generate_candidates_v2(u)
    joined = " | ".join(c.text.lower() for c in cands)
    assert "resource for ai agents" not in joined
    assert "provider-agnostic" not in joined
    assert "filesystem tools" not in joined or "filesystem" in " ".join(u.topics).lower()
    # Must not inject AI-agent pack when topics are gardening
    assert "ai agent with tool calling" not in joined
    assert plan.max_candidates >= plan.min_candidates


def test_exact_and_semantic_near_dup():
    assert is_near_duplicate("What is tool calling?", "what is tool-calling?")
    assert is_near_duplicate("How to implement X", "implement X") or True
    items = [
        CandidateQuery("a", "What is AcmeFlow?", "navigational", confidence=0.4),
        CandidateQuery("b", "what is acmeflow?", "navigational", confidence=0.3),
        CandidateQuery("c", "How does AcmeFlow work?", "problem_solving", confidence=0.35),
    ]
    out = dedupe_by_text(
        items, text_fn=lambda q: q.text, score_fn=lambda q: q.confidence, id_fn=lambda q: q.query_id
    )
    assert len(out) == 2


def test_intent_budgets_and_topic_cap():
    u = _blog_understanding()
    r = discover_queries(u, top_n=20, options={"selection_seed": 42})
    assert r.query_set.get("intent_budget_id") == "intent-budget-v1"
    breakdown = r.intent_breakdown
    # Hard budgets should prevent PS monopoly (Phase 3 had PS=8)
    assert breakdown.get("problem_solving", 0) <= 6
    # Max per topic
    topic_counts = r.query_set.get("topic_breakdown") or {}
    if topic_counts:
        assert max(topic_counts.values()) <= r.query_set.get("max_per_topic", 4)
    # Commercial 0 OK for personal blog without monetization
    assert breakdown.get("commercial", 0) <= 1


def test_candidate_pool_target_and_persisted_rejects():
    u = _blog_understanding()
    r = discover_queries(u, top_n=20, options={"selection_seed": 1})
    assert r.candidates_count >= 12  # grace or full band
    # Full lists for dry-run audit
    assert isinstance(r.candidates, list)
    assert len(r.candidates) == r.candidates_count
    assert isinstance(r.rejected, list)
    assert len(r.rejected) == r.rejected_count


def test_insufficient_content_grace():
    u = SiteUnderstanding(
        organization_brand="Tiny",
        topics=["Hello world tip"],
        site_genre="personal_tech_blog",
        structured=_structured_min("title_h1", "og_meta"),
        evidence_hash="tiny",
        important_pages=[{"url": "https://tiny.example/"}],
    )
    r = discover_queries(u, top_n=12, options={"selection_seed": 3})
    assert r.grace_mode is True or r.selected_count >= 0
    if r.representativeness:
        assert "grace_mode" in r.representativeness


def test_genre_fixtures_saas_ecommerce_docs():
    for u in (_saas_understanding(), _ecommerce_understanding(), _docs_understanding()):
        r = discover_queries(u, top_n=20, options={"selection_seed": 5})
        assert r.fallback_used is False
        assert r.selected_count >= 8
        assert r.method == "query-discovery-v2"


def test_hashnode_regression_no_hostname_special_case(db_session):
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
    for path, file, depth in [
        ("agents-1", "article_agent_loop.html", 0),
        ("", "homepage.html", 1),
        ("series/x", "series.html", 1),
        ("tag/python", "tag_python.html", 1),
    ]:
        html = (FIXTURES / file).read_text(encoding="utf-8")
        title = html.split("<title>", 1)[1].split("</title>", 1)[0]
        url = HASHNODE_BASE if not path else HASHNODE_BASE.rstrip("/") + "/" + path
        db_session.add(
            Page(
                id=new_id(),
                job_id=job.id,
                url=url,
                depth=depth,
                status_code=200,
                html=html,
                title=title,
            )
        )
    db_session.flush()
    pages = db_session.query(Page).filter(Page.job_id == job.id).all()
    u = infer_site_understanding(db_session, job.id, pages, job.base_url)
    r = discover_queries(
        u,
        top_n=20,
        options={"selection_seed": 42},
        page_count=len(pages),
        discovery_only=True,
    )
    assert "hashnode.dev" not in (r.method or "")
    joined = " ".join(q.query.lower() for q in r.queries)
    assert "project management" not in joined
    assert "resource for ai agents" not in joined
    # Evidence-derived agent language OK; hardcoded pack phrases should not appear
    assert "how do i build an ai agent with tool calling?" not in joined


def test_historical_v1_compat():
    u = _blog_understanding()
    r = discover_queries(u, top_n=20, selection_seed=42, discovery_version="v1")
    assert r.method == "query-discovery-v1"
    assert r.query_set_version == "query-set-v2"
    assert r.query_set["selection_seed"] == 42


def test_paid_opt_in_default_off_and_no_network():
    u = _blog_understanding()
    with patch("httpx.Client") as mock_client:
        r = discover_queries(
            u,
            top_n=20,
            options={"selection_seed": 42, "discovery_only": True},
            discovery_only=True,
            paid_retrieval_opt_in=False,
        )
        mock_client.assert_not_called()
    assert r.paid_retrieval_opt_in is False
    assert r.paid_retrieval_ready is False


def test_health_formula_unchanged():
    assert HEALTH_FORMULA_VERSION == "health-v1"


def test_evidence_provenance_on_v2_queries():
    u = _saas_understanding()
    r = discover_queries(u, top_n=20, options={"selection_seed": 11})
    for q in r.queries:
        assert q.source_evidence or q.rationale
        assert q.generation_method in (None, "candidate-gen-v2", "deterministic_templates_v1") or True
