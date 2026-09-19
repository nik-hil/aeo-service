"""Phase 6 — measurement harness + brief gap linkage + fixture before/after."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from aeo_mvp.content.pipeline import run_content_optimization
from aeo_mvp.measurement.before_after import (
    EVIDENCE_CLASSES,
    MEASUREMENT_METHODOLOGY,
    BaselineSnapshot,
    OptimizationMapping,
    PostChangeSnapshot,
    compare_snapshots,
    extract_baseline_from_report,
    extract_coverage_snapshot,
    mappings_from_brief,
)

PHASE6 = Path(__file__).resolve().parents[1] / "fixtures" / "phase6"
HASHNODE = Path(__file__).resolve().parents[1] / "fixtures" / "hashnode"
ARTIFACTS = (
    Path(__file__).resolve().parents[2]
    / "docs"
    / "verification"
    / "artifacts"
    / "phase6"
)


def _qs(*pairs: tuple[str, str]):
    members = []
    for i, (qid, text) in enumerate(pairs, start=1):
        members.append(
            {
                "selection_rank": i,
                "query": {
                    "query_id": qid,
                    "text": text,
                    "intent": "informational",
                    "topic": text.split()[0].lower(),
                },
                "gate": {"accepted": True},
            }
        )
    return {
        "query_set_id": "qs_phase6_test",
        "query_set_version": "query-set-v3",
        "fingerprint": "test-fp",
        "selection_seed": 42,
        "members": members,
        "paid_retrieval_opt_in": False,
    }


def test_measurement_methodology_constant():
    assert MEASUREMENT_METHODOLOGY == "aeo-before-after-v1"
    assert "hypothesis" in EVIDENCE_CLASSES
    assert "causal_evidence" in EVIDENCE_CLASSES


def test_extract_baseline_from_phase4_shaped_report():
    report = {
        "job_id": "a24c1a42-test",
        "base_url": "https://nik-hil.hashnode.dev/",
        "emitted_at": "2026-09-18T00:00:00Z",
        "discovered_queries": {
            "query_set_version": "query-set-v3",
            "fingerprint": "8547b8bb",
            "selected_count": 20,
            "paid_retrieval_opt_in": True,
            "query_set": {
                "query_set_version": "query-set-v3",
                "fingerprint": "8547b8bb",
                "selection_seed": 42,
            },
        },
        "experiment": {
            "provider_name": "digitalocean_web_search",
            "experiment_kind": "ai_search_visibility",
            "retrieval_enabled": True,
        },
        "paid_retrieval": True,
        "visibility_obs": {"n": 20, "appeared": 17, "cited": 17},
        "metrics": {
            "ai_search_citation_rate": {"value": 0.85, "provenance": "estimate"},
            "ai_search_mention_rate": {"value": 0.7, "provenance": "estimate"},
        },
    }
    snap = extract_baseline_from_report(report, source="unit")
    assert snap.visibility_mode == "ai_search"
    assert snap.appeared_count == 17
    assert snap.cited_count == 17
    assert snap.appearance_rate == pytest.approx(0.85)
    assert snap.citation_rate == 0.85
    assert snap.selection_seed == 42
    assert snap.paid_retrieval is True


def test_demo_visibility_never_claims_ai_search():
    report = {
        "base_url": "https://nik-hil.hashnode.dev/",
        "experiment": {
            "provider_name": "demo",
            "experiment_kind": "llm_mention",
            "retrieval_enabled": False,
        },
        "discovered_queries": {"selected_count": 5, "query_set_version": "query-set-v3"},
    }
    snap = extract_baseline_from_report(report)
    assert snap.visibility_mode == "demo_synthetic"
    assert any("synthetic" in w.lower() or "demo" in w.lower() for w in snap.warnings)


def test_fixture_simulated_comparison_is_hypothesis():
    b = extract_coverage_snapshot(
        page_url="https://nik-hil.hashnode.dev/",
        coverage_summary={"queries": 4, "covered": 2, "gapped": 2, "gap_count": 3},
        gap_count=3,
        query_set_version="query-set-v3",
        fingerprint="fp",
        selection_seed=42,
    )
    p = PostChangeSnapshot.from_baseline(
        extract_coverage_snapshot(
            page_url="https://nik-hil.hashnode.dev/",
            coverage_summary={"queries": 4, "covered": 4, "gapped": 0, "gap_count": 1},
            gap_count=1,
            query_set_version="query-set-v3",
            fingerprint="fp",
            selection_seed=42,
        ),
        change_source="fixture_simulated",
        applied_recommendation_ids=["home_add_h1"],
    )
    cmp = compare_snapshots(
        b,
        p,
        mappings=[
            OptimizationMapping(
                recommendation_id="home_add_h1",
                page_url="https://nik-hil.hashnode.dev/",
                problem="missing H1",
                recommended_change="add h1",
                website_change="inserted h1",
                queries_affected=["q1"],
            )
        ],
    )
    assert cmp.evidence_class == "hypothesis"
    assert "CMS" in cmp.evidence_rationale or any("CMS" in c for c in cmp.caveats)
    assert cmp.deltas["coverage"]["covered"]["delta"] == 2


def test_parity_mismatch_downgrades_observed_to_correlation():
    b = BaselineSnapshot(
        target_domain="https://nik-hil.hashnode.dev/",
        query_set_version="query-set-v3",
        query_set_fingerprint="aaa",
        selection_seed=42,
        provider="digitalocean_web_search",
        experiment_kind="ai_search_visibility",
        visibility_mode="ai_search",
        n_queries=20,
        appeared_count=10,
        cited_count=10,
        appearance_rate=0.5,
        citation_rate=0.5,
    )
    p = PostChangeSnapshot.from_baseline(
        BaselineSnapshot(
            target_domain="https://nik-hil.hashnode.dev/",
            query_set_version="query-set-v3",
            query_set_fingerprint="bbb",  # mismatch
            selection_seed=42,
            provider="digitalocean_web_search",
            experiment_kind="ai_search_visibility",
            visibility_mode="ai_search",
            n_queries=20,
            appeared_count=15,
            cited_count=15,
            appearance_rate=0.75,
            citation_rate=0.75,
        ),
        change_source="live_cms",
    )
    cmp = compare_snapshots(b, p)
    assert cmp.evidence_class == "correlation"
    assert cmp.methodology_parity["fingerprint_match"] is False


def test_brief_work_queue_links_schema_gap_ids():
    html = (HASHNODE / "homepage.html").read_text(encoding="utf-8")
    # Ensure missing H1 path if fixture has no h1
    if "<h1" in html.lower():
        html = html.replace("<h1", "<h2").replace("</h1>", "</h2>")
    result = run_content_optimization(
        html=html,
        url="https://nik-hil.hashnode.dev/",
        queryset=_qs(
            ("q1", "Where can I find content from Nikhil Ikhar?"),
            ("q2", "How do you build an AI agent with tool calling?"),
        ),
        site_profile={"site_genre": {"value": "personal_tech_blog"}},
        generate_draft=False,
    )
    wire = result.to_dict()
    gaps = wire["content_gaps"][0]["gaps"]
    assert any(g["gap_type"] == "schema_gap" for g in gaps) or any(
        "h1" in (g.get("rationale") or "").lower() for g in gaps
    )
    brief = wire["optimization_briefs"][0]
    h1_ops = [w for w in brief["work_queue"] if w.get("target") == "h1"]
    assert h1_ops, "expected add/expand h1 work item"
    assert h1_ops[0].get("related_gap_ids"), "H1 work item must link related_gap_ids"


def test_phase6_html_fixtures_exist_and_optimize():
    assert (PHASE6 / "homepage_baseline.html").is_file()
    assert (PHASE6 / "homepage_optimized.html").is_file()
    assert (PHASE6 / "article_agent1_baseline.html").is_file()
    assert (PHASE6 / "article_agent1_optimized.html").is_file()
    base = (PHASE6 / "homepage_baseline.html").read_text(encoding="utf-8")
    opt = (PHASE6 / "homepage_optimized.html").read_text(encoding="utf-8")
    assert "<h1" not in base.lower() or "Nikhil Ikhar's blog — AI agents" not in base
    assert "Nikhil Ikhar's blog — AI agents" in opt
    b = run_content_optimization(
        html=base,
        url="https://nik-hil.hashnode.dev/",
        queryset=_qs(("q1", "Where can I find content from Nikhil Ikhar?")),
        generate_draft=True,
    )
    o = run_content_optimization(
        html=opt,
        url="https://nik-hil.hashnode.dev/",
        queryset=_qs(("q1", "Where can I find content from Nikhil Ikhar?")),
        generate_draft=True,
    )
    assert o.page_intelligence.h1
    assert b.to_dict()["content_drafts"][0]["content_provenance"] == "generated"
    # Optimized should not increase gap_count
    assert (o.to_dict()["content_gaps"][0]["gap_count"] or 0) <= (
        b.to_dict()["content_gaps"][0]["gap_count"] or 0
    )


def test_mappings_from_brief_include_query_and_gap_refs():
    brief = {
        "brief_id": "b1",
        "target_url": "https://nik-hil.hashnode.dev/",
        "action": "add_schema",
        "work_queue": [
            {
                "action": "add",
                "target": "h1",
                "reason": "H1 missing",
                "related_gap_ids": ["gap_schema_1"],
                "related_query_ids": ["q1"],
            }
        ],
    }
    maps = mappings_from_brief(brief)
    assert len(maps) == 1
    assert maps[0].evidence_refs == ["gap_schema_1"]
    assert maps[0].queries_affected == ["q1"]


def test_live_phase6_artifact_present_if_committed():
    summary = ARTIFACTS / "PHASE6_HASHNODE_JOB_SUMMARY.json"
    if not summary.is_file():
        pytest.skip("Phase 6 live artifact not present in tree")
    data = json.loads(summary.read_text(encoding="utf-8"))
    assert data.get("paid_retrieval_opt_in") is False
    assert data.get("adr026_gate") == "closed"
    assert "hashnode" in (data.get("base_url") or "")
