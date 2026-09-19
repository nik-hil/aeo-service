#!/usr/bin/env python3
"""Simulate post-change content optimization on Phase 6 HTML fixtures.

Applies recommended edits offline (no CMS publish), re-runs Phase 5 gap analysis,
and writes a before/after comparison under docs/verification/artifacts/phase6/.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from aeo_mvp.content.pipeline import run_content_optimization  # noqa: E402
from aeo_mvp.measurement.before_after import (  # noqa: E402
    OptimizationMapping,
    PostChangeSnapshot,
    compare_snapshots,
    extract_coverage_snapshot,
    mappings_from_brief,
)

FIXTURES = ROOT / "tests" / "fixtures" / "phase6"
OUT = ROOT / "docs" / "verification" / "artifacts" / "phase6"

# Representative probes aligned with Hashnode agent-series themes (fixture path).
QUERYSET = {
    "query_set_id": "qs_phase6_fixture",
    "query_set_version": "query-set-v3",
    "fingerprint": "phase6-fixture-fp-v1",
    "selection_seed": 42,
    "paid_retrieval_opt_in": False,
    "members": [
        {
            "selection_rank": 1,
            "query": {
                "query_id": "q_agent_loop",
                "text": "What is an agent loop in AI agents?",
                "intent": "informational",
                "topic": "agent loop",
            },
            "gate": {"accepted": True},
        },
        {
            "selection_rank": 2,
            "query": {
                "query_id": "q_tool_calling",
                "text": "How do you build an AI agent with tool calling?",
                "intent": "problem_solving",
                "topic": "tool calling",
            },
            "gate": {"accepted": True},
        },
        {
            "selection_rank": 3,
            "query": {
                "query_id": "q_resources",
                "text": "What are good resources for learning AI agent tool calling?",
                "intent": "recommendation",
                "topic": "learning resources",
            },
            "gate": {"accepted": True},
        },
        {
            "selection_rank": 4,
            "query": {
                "query_id": "q_nikhil",
                "text": "Where can I find content from Nikhil Ikhar?",
                "intent": "navigational",
                "topic": "brand",
            },
            "gate": {"accepted": True},
        },
    ],
}

PROFILE = {
    "site_genre": {"value": "personal_tech_blog"},
    "org_name": {"value": "Nikhil Ikhar"},
}


def _run(html: str, url: str):
    return run_content_optimization(
        html=html,
        url=url,
        queryset=QUERYSET,
        site_profile=PROFILE,
        generate_draft=True,
        draft_paid=False,
    )


def main() -> int:
    home_b = (FIXTURES / "homepage_baseline.html").read_text(encoding="utf-8")
    home_o = (FIXTURES / "homepage_optimized.html").read_text(encoding="utf-8")
    art_b = (FIXTURES / "article_agent1_baseline.html").read_text(encoding="utf-8")
    art_o = (FIXTURES / "article_agent1_optimized.html").read_text(encoding="utf-8")

    pages = [
        (
            "homepage",
            "https://nik-hil.hashnode.dev/",
            home_b,
            home_o,
            [
                OptimizationMapping(
                    recommendation_id="home_add_h1",
                    page_url="https://nik-hil.hashnode.dev/",
                    problem="Missing H1 on homepage (schema_gap / extractability)",
                    recommended_change="add h1",
                    website_change="Inserted H1 + short answer-first intro (fixture)",
                    queries_affected=["q_nikhil"],
                    expected_effect="Clearer brand/topic extractability on homepage",
                    evidence_refs=["gap_metadata"],
                )
            ],
        ),
        (
            "article_agent1",
            "https://nik-hil.hashnode.dev/agents-zero-to-hero-1-building-an-ai-agent-from-scratch-with-tool-calling",
            art_b,
            art_o,
            [
                OptimizationMapping(
                    recommendation_id="article_answer_first_faq",
                    page_url="https://nik-hil.hashnode.dev/agents-zero-to-hero-1-building-an-ai-agent-from-scratch-with-tool-calling",
                    problem="Thin/partial coverage for agent-loop and tool-calling probes; weak FAQ/schema signals",
                    recommended_change="expand_section + add_faq + FAQPage schema",
                    website_change="Added answer-first section, FAQ block, FAQPage JSON-LD (fixture)",
                    queries_affected=["q_agent_loop", "q_tool_calling", "q_resources"],
                    expected_effect="Raise page_coverage and FAQ/schema extractability for linked queries",
                    evidence_refs=["thin_coverage", "no_answer_block"],
                )
            ],
        ),
    ]

    results = []
    for label, url, base_html, opt_html, maps in pages:
        base = _run(base_html, url)
        opt = _run(opt_html, url)
        b_dict = base.to_dict()
        o_dict = opt.to_dict()
        b_gap = b_dict["content_gaps"][0]
        o_gap = o_dict["content_gaps"][0]
        b_snap = extract_coverage_snapshot(
            page_url=url,
            coverage_summary=b_gap.get("coverage_summary") or {},
            gap_count=int(b_gap.get("gap_count") or len(b_gap.get("gaps") or [])),
            query_set_version="query-set-v3",
            fingerprint="phase6-fixture-fp-v1",
            selection_seed=42,
            label=f"{label}_baseline",
        )
        p_cov = extract_coverage_snapshot(
            page_url=url,
            coverage_summary=o_gap.get("coverage_summary") or {},
            gap_count=int(o_gap.get("gap_count") or len(o_gap.get("gaps") or [])),
            query_set_version="query-set-v3",
            fingerprint="phase6-fixture-fp-v1",
            selection_seed=42,
            label=f"{label}_post",
        )
        p_snap = PostChangeSnapshot.from_baseline(
            p_cov,
            change_source="fixture_simulated",
            applied_recommendation_ids=[m.recommendation_id for m in maps],
        )
        # Prefer brief-derived mappings when present
        brief_maps = mappings_from_brief(o_dict["optimization_briefs"][0])
        cmp = compare_snapshots(b_snap, p_snap, mappings=maps or brief_maps)
        results.append(
            {
                "label": label,
                "url": url,
                "baseline_page_intelligence": {
                    k: b_dict["page_intelligence"].get(k)
                    for k in (
                        "url",
                        "title",
                        "content_type",
                        "word_count",
                        "schema_types",
                        "h1",
                    )
                },
                "post_page_intelligence": {
                    k: o_dict["page_intelligence"].get(k)
                    for k in (
                        "url",
                        "title",
                        "content_type",
                        "word_count",
                        "schema_types",
                        "h1",
                    )
                },
                "baseline_coverage": b_gap.get("coverage_summary"),
                "post_coverage": o_gap.get("coverage_summary"),
                "baseline_gap_count": b_gap.get("gap_count"),
                "post_gap_count": o_gap.get("gap_count"),
                "baseline_gaps_sample": (b_gap.get("gaps") or [])[:5],
                "post_gaps_sample": (o_gap.get("gaps") or [])[:5],
                "post_brief_action": o_dict["optimization_briefs"][0].get("action"),
                "post_work_queue_sample": (
                    o_dict["optimization_briefs"][0].get("work_queue") or []
                )[:6],
                "draft_provenance": o_dict["content_drafts"][0].get(
                    "content_provenance"
                ),
                "draft_status": o_dict["content_drafts"][0].get("status"),
                "comparison": cmp.to_dict(),
                "mappings": [m.to_dict() for m in maps],
            }
        )

    OUT.mkdir(parents=True, exist_ok=True)
    payload = {
        "methodology": "aeo-before-after-v1",
        "change_source": "fixture_simulated",
        "paid_retrieval": False,
        "live_cms_publish": False,
        "queryset": {
            "query_set_id": QUERYSET["query_set_id"],
            "query_set_version": QUERYSET["query_set_version"],
            "fingerprint": QUERYSET["fingerprint"],
            "selection_seed": QUERYSET["selection_seed"],
            "n_queries": len(QUERYSET["members"]),
        },
        "pages": results,
    }
    out_path = OUT / "PHASE6_FIXTURE_BEFORE_AFTER.json"
    out_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"wrote": str(out_path), "pages": [
        {
            "label": r["label"],
            "gap_count": [r["baseline_gap_count"], r["post_gap_count"]],
            "coverage": [r["baseline_coverage"], r["post_coverage"]],
            "evidence_class": r["comparison"]["evidence_class"],
            "h1": [
                r["baseline_page_intelligence"].get("h1"),
                r["post_page_intelligence"].get("h1"),
            ],
        }
        for r in results
    ]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
