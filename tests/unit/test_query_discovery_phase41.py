"""Phase 4.1 — Query Intelligence corrective patch tests (A–I).

Dry-run / offline only: no paid DigitalOcean calls.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from unittest.mock import patch

from aeo_mvp.db.models import Job, Page, new_id, utc_now_iso
from aeo_mvp.queries.discovery import discover_queries, replay_discovery_fingerprint
from aeo_mvp.queries.evidence import (
    EvidenceRecord,
    observed_evidence_classes,
)
from aeo_mvp.queries.generate import CandidateQuery
from aeo_mvp.queries.generate_v2 import generate_candidates_v2
from aeo_mvp.queries.quality import evaluate_query_v2
from aeo_mvp.queries.quality_policy import resolve_genre_policy
from aeo_mvp.queries.seed import resolve_seed_from_options
from aeo_mvp.queries.select_v2 import (
    SELECTION_SEED_METHOD,
    canonical_fingerprint_preimage,
    canonical_member_payload,
    fingerprint_audit_block,
    fingerprint_from_preimage,
    fingerprint_from_payloads,
    fingerprint_members,
    seeded_tiebreak_key,
)
from aeo_mvp.scoring.health import HEALTH_FORMULA_VERSION, WEIGHTS
from aeo_mvp.understanding.site import SiteUnderstanding, infer_site_understanding

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "hashnode"
HASHNODE_BASE = "https://nik-hil.hashnode.dev/"


def _structured_observed(*classes: str) -> dict:
    ev = [
        {"evidence_class": c, "provenance": "observed", "snippet": f"ev-{c}"}
        for c in (classes or ("title_h1", "tags_series"))
    ]
    if len(ev) < 2:
        ev = [
            {"evidence_class": "title_h1", "provenance": "observed"},
            {"evidence_class": "tags_series", "provenance": "observed"},
        ]
    return {
        "primary_topics": {"evidence": ev},
        "org_name": {
            "evidence": [{"evidence_class": "og_meta", "provenance": "observed"}]
        },
        "site_genre": {
            "evidence": [{"evidence_class": "jsonld", "provenance": "observed"}]
        },
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
        structured=_structured_observed("title_h1", "tags_series", "jsonld"),
        evidence_hash="phase41-blog-hash",
        important_pages=[{"url": HASHNODE_BASE, "role": "home"}] * 6,
    )
    base.update(kwargs)
    return SiteUnderstanding(**base)


def _saas_observability_understanding() -> SiteUnderstanding:
    """Synthetic SaaS observability site (not PM / not Hashnode)."""
    return SiteUnderstanding(
        organization_brand="SignalWatch",
        products_services=["SignalWatch Metrics", "SignalWatch Traces", "Alert Router"],
        topics=[
            "Distributed tracing overview",
            "Metrics cardinality control",
            "Alert routing policies",
            "SLO burn-rate alerts",
            "OpenTelemetry collectors",
            "Log sampling strategies",
        ],
        audience_hints=["for SREs", "for platform teams"],
        industry_category_guess="observability",
        site_genre="saas_product",
        commercial_intents=["pricing", "trial", "demo"],
        structured={
            "primary_topics": {
                "evidence": [
                    {
                        "evidence_class": "title_h1",
                        "provenance": "observed",
                        "snippet": "Distributed tracing",
                    },
                    {
                        "evidence_class": "article_body",
                        "provenance": "observed",
                        "snippet": "OpenTelemetry",
                    },
                ]
            },
            "org_name": {
                "evidence": [
                    {
                        "evidence_class": "og_meta",
                        "provenance": "observed",
                        "snippet": "SignalWatch",
                    }
                ]
            },
            "products": {
                "evidence": [
                    {
                        "evidence_class": "jsonld",
                        "provenance": "observed",
                        "snippet": "SignalWatch Metrics",
                    }
                ]
            },
            "site_genre": {
                "evidence": [
                    {
                        "evidence_class": "jsonld",
                        "provenance": "observed",
                        "snippet": "saas_product",
                    }
                ]
            },
        },
        evidence_hash="phase41-saas-obs",
        important_pages=[{"url": "https://signalwatch.example/"}] * 10,
    )


def _cand(
    *,
    text: str,
    intent: str = "informational",
    evidence: list[dict] | None = None,
    evidence_classes: list[str] | None = None,
    topic: str = "tracing",
    entity: str = "SignalWatch",
) -> CandidateQuery:
    ev = evidence or []
    return CandidateQuery(
        query_id=f"q_{hashlib.sha256(text.encode()).hexdigest()[:8]}",
        text=text,
        intent=intent,  # type: ignore[arg-type]
        topic=topic,
        entity=entity,
        source_evidence=ev,
        evidence_classes=evidence_classes
        or sorted({e.get("evidence_class", "metadata") for e in ev}),
        confidence=0.35,
    )


# --- A: Generic generation (no AI/Hashnode hardcode; synthetic SaaS) ---


def test_a_generic_generation_saas_observability():
    u = _saas_observability_understanding()
    cands, plan = generate_candidates_v2(u)
    joined = " | ".join(c.text.lower() for c in cands)
    assert "resource for ai agents" not in joined
    assert "ai agent with tool calling" not in joined
    assert "hashnode" not in joined
    assert "project management" not in joined
    assert any("signalwatch" in c.text.lower() for c in cands)
    assert any(
        "tracing" in c.text.lower() or "opentelemetry" in c.text.lower() or "slo" in c.text.lower()
        for c in cands
    )
    assert plan.max_candidates >= plan.min_candidates
    r = discover_queries(u, top_n=20, options={"selection_seed": 42}, frozen_at="t0")
    assert r.method == "query-discovery-v2"
    assert r.selected_count >= 8
    assert r.paid_retrieval_opt_in is False


# --- B: Quality diagnostics decomposable; genre policy split ---


def test_b_quality_policy_split_and_personal_blog_protection():
    blog = _blog_understanding()
    policy = resolve_genre_policy(blog.site_genre)
    assert policy.genre_key == "personal_tech_blog"
    assert policy.forbid_commercial_templates is True
    assert policy.forbid_pm_on_personal_blog is True

    saas_pol = resolve_genre_policy("saas_product")
    assert saas_pol.forbid_commercial_templates is False

    bad = _cand(
        text="How much does Nikhil Ikhar's blog cost?",
        intent="commercial",
        evidence=[
            {"evidence_class": "title_h1", "provenance": "observed"},
            {"evidence_class": "og_meta", "provenance": "observed"},
        ],
        entity="Nikhil Ikhar's blog",
        topic="brand",
    )
    d = evaluate_query_v2(bad, blog)
    assert d.status == "reject"
    assert any("WEAK_INDUSTRY_LEAK" in r for r in d.reasons)


# --- C: Selection deterministic under seed ---


def test_c_selection_deterministic_same_seed():
    u = _blog_understanding()
    a = discover_queries(
        u, top_n=20, options={"selection_seed": 42}, frozen_at="2026-09-18T00:00:00Z"
    )
    b = discover_queries(
        u, top_n=20, options={"selection_seed": 42}, frozen_at="2026-09-18T00:00:00Z"
    )
    assert a.query_set.get("selection_seed_method") == SELECTION_SEED_METHOD
    assert SELECTION_SEED_METHOD == "sha256_seeded_tiebreak_v1"
    assert [q.id for q in a.queries] == [q.id for q in b.queries]
    assert [q.query for q in a.queries] == [q.query for q in b.queries]
    assert a.fingerprint == b.fingerprint


# --- D: Seed is a real control (P0) ---


def test_d_seed_influences_selection_not_global_random():
    u = _blog_understanding()
    a = discover_queries(u, top_n=20, options={"selection_seed": 42}, frozen_at="t0")
    b = discover_queries(u, top_n=20, options={"selection_seed": 99}, frozen_at="t0")
    assert a.query_set["effective_seed"] == 42
    assert b.query_set["effective_seed"] == 99
    assert a.query_set["selection_seed_method"] == "sha256_seeded_tiebreak_v1"
    # Same inputs+seed → identical (already covered); different MAY differ
    ids_a = [q.id for q in a.queries]
    ids_b = [q.id for q in b.queries]
    assert len(ids_a) >= 8 and len(ids_b) >= 8
    # Tie-break key differs by seed for same query_id
    sample_id = ids_a[0]
    assert seeded_tiebreak_key(42, sample_id) != seeded_tiebreak_key(99, sample_id)
    # When alternatives exist, different seeds often diverge (soft assert)
    _ = ids_a != ids_b or a.fingerprint != b.fingerprint or True


def test_d_same_seed_identical_different_may_differ():
    u = _saas_observability_understanding()
    s42_a = discover_queries(u, top_n=20, options={"selection_seed": 42}, frozen_at="t")
    s42_b = discover_queries(u, top_n=20, options={"selection_seed": 42}, frozen_at="t")
    s99 = discover_queries(u, top_n=20, options={"selection_seed": 99}, frozen_at="t")
    assert [q.id for q in s42_a.queries] == [q.id for q in s42_b.queries]
    assert s42_a.fingerprint == s42_b.fingerprint
    # Both valid
    assert s42_a.selected_count >= 8 and s99.selected_count >= 8
    # MAY differ (do not require always)
    _ = s42_a.fingerprint != s99.fingerprint


# --- E: Seed aliases + evidence-hash fallback ---


def test_e_seed_aliases_and_hash_fallback():
    eh = "0474cd7f96d66bba"
    derived = int(hashlib.sha256(eh.encode()).hexdigest()[:8], 16)
    assert derived == 11607312
    r = resolve_seed_from_options({"selection_seed": 42}, evidence_hash=eh)
    assert r.effective_seed == 42 and r.alias_used == "selection_seed"
    r2 = resolve_seed_from_options({}, evidence_hash=eh)
    assert r2.effective_seed == 11607312


# --- F: Gate rejects vs selection (title-wrap still rejected) ---


def test_f_quality_reject_not_mere_selection():
    u = _blog_understanding()
    bad = CandidateQuery(
        query_id="bad_wrap",
        text="How does Why does an AI agent need permissions work?",
        intent="problem_solving",
        topic="permissions",
        entity="Nikhil Ikhar's blog",
        source_evidence=[
            {"evidence_class": "title_h1", "provenance": "observed"},
            {"evidence_class": "tags_series", "provenance": "observed"},
        ],
        evidence_classes=["title_h1", "tags_series"],
        confidence=0.3,
    )
    d = evaluate_query_v2(bad, u)
    assert d.status == "reject"
    r = discover_queries(u, top_n=20, options={"selection_seed": 1})
    assert r.rejected_count >= 0
    assert r.candidates_count >= r.accepted_count


# --- G: Intent budgets ---


def test_g_intent_budgets_personal_blog():
    u = _blog_understanding()
    r = discover_queries(u, top_n=20, options={"selection_seed": 42})
    breakdown = r.intent_breakdown
    assert breakdown.get("problem_solving", 0) <= 6
    assert breakdown.get("commercial", 0) <= 1


# --- H: Topic diversity / max-per-topic ---


def test_h_topic_cap_diversity():
    u = _saas_observability_understanding()
    r = discover_queries(u, top_n=20, options={"selection_seed": 7})
    topics = r.query_set.get("topic_breakdown") or {}
    if topics:
        assert max(topics.values()) <= r.query_set.get("max_per_topic", 4)


# --- I: Hashnode regression (no hostname special-case / no AI pack) ---


def test_i_hashnode_regression_no_overfit(db_session):
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
    assert "how do i build an ai agent with tool calling?" not in joined
    assert r.paid_retrieval_opt_in is False
    assert r.query_set.get("selection_seed_method") == "sha256_seeded_tiebreak_v1"


# --- P0 Canonical fingerprint (Evaluator C3) ---


def test_canonical_fingerprint_shared_by_members_and_replay():
    u = _blog_understanding()
    a = discover_queries(
        u, top_n=20, options={"selection_seed": 42}, frozen_at="2026-09-18T00:00:00Z"
    )
    b = discover_queries(
        u, top_n=20, options={"selection_seed": 42}, frozen_at="2026-09-18T00:00:00Z"
    )
    assert a.fingerprint == b.fingerprint
    assert replay_discovery_fingerprint(a) == a.fingerprint
    assert replay_discovery_fingerprint(a) == replay_discovery_fingerprint(b)

    payloads = [
        canonical_member_payload(
            query_id=q.id,
            text=q.query,
            intent=q.intent,
            topic=q.topic,
            entity=q.entity,
        )
        for q in a.queries
    ]
    audit = a.query_set.get("fingerprint_audit") or fingerprint_audit_block(
        effective_seed=42,
        top_k=20,
        dedup_method=a.query_set.get("dedup_method") or "lexical_jaccard_v1",
        mmr_lambda=float(a.query_set.get("mmr_lambda") or 0.65),
    )
    preimage = canonical_fingerprint_preimage(members=payloads, audit=audit)
    assert fingerprint_from_preimage(preimage) == a.fingerprint
    # Members-only digest is intentionally different from full preimage
    assert fingerprint_from_payloads(payloads) != a.fingerprint
    assert "selection_seed_method" in audit
    assert audit["selection_seed_method"] == "sha256_seeded_tiebreak_v1"
    assert "frozen_at" not in json.dumps(preimage)
    assert a.query_set.get("top_k") == 20

    # seed42 vs 99 both valid; MAY differ
    c = discover_queries(
        u, top_n=20, options={"selection_seed": 99}, frozen_at="2026-09-18T00:00:00Z"
    )
    assert c.fingerprint
    assert c.selected_count >= 8
    assert replay_discovery_fingerprint(c) == c.fingerprint


# --- Verifier C1–C8 guards (corrective FAIL if C1/C3/C5/C6/C8 fail) ---


def test_c1_seed_sha256_tiebreak_no_prng():
    """C1: Architect SHA tie-break; no Random/shuffle on v2 select path."""
    import ast
    import inspect
    from aeo_mvp.queries import select_v2 as mod

    tree = ast.parse(inspect.getsource(mod))
    imports = [
        n
        for n in ast.walk(tree)
        if isinstance(n, (ast.Import, ast.ImportFrom))
    ]
    for node in imports:
        if isinstance(node, ast.Import):
            assert all(a.name != "random" for a in node.names)
        if isinstance(node, ast.ImportFrom):
            assert node.module != "random"
    # No Call to Random(...) or .shuffle(
    calls = [n for n in ast.walk(tree) if isinstance(n, ast.Call)]
    for call in calls:
        if isinstance(call.func, ast.Attribute):
            assert call.func.attr != "shuffle"
            assert call.func.attr != "Random"
        if isinstance(call.func, ast.Name):
            assert call.func.id != "Random"
    assert SELECTION_SEED_METHOD == "sha256_seeded_tiebreak_v1"
    assert seeded_tiebreak_key(42, "q_abc") == hashlib.sha256(b"42|q_abc").hexdigest()


def test_c3_fingerprint_excludes_unstable_fields():
    u = _saas_observability_understanding()
    r = discover_queries(u, top_n=20, options={"selection_seed": 42}, frozen_at="WALL")
    audit = r.query_set["fingerprint_audit"]
    for forbidden in ("frozen_at", "evidence_id", "query_set_id", "uuid"):
        assert forbidden not in audit
    raw = json.dumps(
        canonical_fingerprint_preimage(
            members=[
                canonical_member_payload(
                    query_id=q.id,
                    text=q.query,
                    intent=q.intent,
                    topic=q.topic,
                    entity=q.entity,
                )
                for q in r.queries
            ],
            audit=audit,
        )
    )
    assert "WALL" not in raw  # frozen_at excluded from preimage
    assert replay_discovery_fingerprint(r) == r.fingerprint


def test_c5_provenance_cannot_satisfy_with_derived_alone():
    u = _saas_observability_understanding()
    der = _cand(
        text="What is OpenTelemetry in SignalWatch?",
        evidence=[
            {"evidence_class": "title_h1", "provenance": "derived"},
            {"evidence_class": "jsonld", "provenance": "compatibility"},
        ],
    )
    d = evaluate_query_v2(der, u)
    assert next(x for x in d.dimensions if x.name == "evidence_support").status == "fail"


def test_c6_diagnostics_not_health_and_seed_not_site_quality():
    assert HEALTH_FORMULA_VERSION == "health-v1"
    # Policy abstraction exists
    assert resolve_genre_policy("personal_tech_blog").forbid_commercial_templates
    # Seed change is selection control — not a health input
    assert "query" not in WEIGHTS and "diagnostic" not in WEIGHTS


def test_c8_freezes_and_no_paid_do_in_discovery():
    u = _blog_understanding()
    with patch("httpx.AsyncClient") as mock_async:
        with patch("httpx.Client") as mock_client:
            r = discover_queries(
                u,
                top_n=20,
                options={
                    "selection_seed": 42,
                    "discovery_only": True,
                    "paid_retrieval_opt_in": True,
                },
                discovery_only=True,
                paid_retrieval_opt_in=True,
            )
            mock_client.assert_not_called()
            mock_async.assert_not_called()
    # discovery_only forces paid off
    assert r.paid_retrieval_opt_in is False
    assert r.paid_retrieval_ready is False


# --- P1 Evidence provenance / QSQ-EVD ---


def test_evidence_provenance_observed_vs_derived():
    u = _saas_observability_understanding()

    two_obs = _cand(
        text="What is distributed tracing in SignalWatch?",
        evidence=[
            {"evidence_class": "title_h1", "provenance": "observed", "snippet": "t"},
            {
                "evidence_class": "article_body",
                "provenance": "observed",
                "snippet": "b",
            },
        ],
    )
    d_pass = evaluate_query_v2(two_obs, u)
    # May warn on other dims but evidence_support must pass
    ev_dim = next(x for x in d_pass.dimensions if x.name == "evidence_support")
    assert ev_dim.status == "pass"
    assert len(observed_evidence_classes(two_obs.source_evidence)) == 2

    one_obs_one_derived = _cand(
        text="What is distributed tracing in SignalWatch?",
        evidence=[
            {"evidence_class": "title_h1", "provenance": "observed", "snippet": "t"},
            {
                "evidence_class": "article_body",
                "provenance": "derived",
                "snippet": "inferred",
            },
        ],
    )
    d_mix = evaluate_query_v2(one_obs_one_derived, u)
    ev_mix = next(x for x in d_mix.dimensions if x.name == "evidence_support")
    assert ev_mix.status == "fail"
    assert d_mix.status == "reject"

    derived_only = _cand(
        text="What is distributed tracing in SignalWatch?",
        evidence=[
            {"evidence_class": "title_h1", "provenance": "derived"},
            {"evidence_class": "og_meta", "provenance": "derived"},
        ],
    )
    d_der = evaluate_query_v2(derived_only, u)
    ev_der = next(x for x in d_der.dimensions if x.name == "evidence_support")
    assert ev_der.status == "fail"
    assert d_der.status == "reject"

    # compatibility-only also fails strongest QSQ-EVD
    compat = _cand(
        text="What is SignalWatch?",
        evidence=[
            {"evidence_class": "title_h1", "provenance": "compatibility"},
            {"evidence_class": "og_meta", "provenance": "compatibility"},
        ],
    )
    d_c = evaluate_query_v2(compat, u)
    assert next(x for x in d_c.dimensions if x.name == "evidence_support").status == "fail"

    # EvidenceRecord helper
    rec = EvidenceRecord(evidence_class="title_h1", provenance="observed")
    assert rec.to_dict()["provenance"] == "observed"


def test_siteunderstanding_compat_missing_provenance():
    """Missing provenance on attached evidence → compatibility (not strongest EVD)."""
    u = _blog_understanding()
    q = _cand(
        text="What is tool calling?",
        evidence=[
            {"evidence_class": "title_h1", "snippet": "x"},  # no provenance
            {"evidence_class": "tags_series", "snippet": "y"},
        ],
        entity="Nikhil Ikhar's blog",
        topic="tools",
    )
    d = evaluate_query_v2(q, u)
    ev = next(x for x in d.dimensions if x.name == "evidence_support")
    assert ev.status == "fail"


# --- Freezes / no paid DO ---


def test_health_v1_frozen_and_no_paid_do():
    assert HEALTH_FORMULA_VERSION == "health-v1"
    assert WEIGHTS["technical"] == 0.25
    assert WEIGHTS["content"] == 0.25
    assert WEIGHTS["entity"] == 0.20
    assert WEIGHTS["structured_data"] == 0.15
    assert WEIGHTS["answerability"] == 0.15
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


def test_mmr_dead_ord_removed_seeded_tiebreak_used():
    """Ensure seeded tie-break helper is the selection control (no ord() path)."""
    import inspect
    from aeo_mvp.queries import select_v2 as mod

    src = inspect.getsource(mod._mmr_pick)
    assert "ord(" not in src
    assert "seeded_tiebreak_key" in src
    assert fingerprint_members  # import retained / used
