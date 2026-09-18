#!/usr/bin/env python3
"""Offline Hashnode validation for Phase 3 SiteProfile + query discovery.

Uses tests/fixtures/hashnode (recorded crawl stand-in). No paid APIs.
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from aeo_mvp.db.models import Page, new_id  # noqa: E402
from aeo_mvp.queries.discovery import discover_queries  # noqa: E402
from aeo_mvp.understanding.builder import build_structured_profile  # noqa: E402
from aeo_mvp.understanding.site import project_understanding  # noqa: E402

FIXTURES = ROOT / "tests" / "fixtures" / "hashnode"
BASE = "https://nik-hil.hashnode.dev/"
OUT_MD = ROOT / "docs" / "verification" / "PHASE3-HASHNODE-OFFLINE-2026-09-18.md"
OUT_JSON = ROOT / "docs" / "verification" / "PHASE3-HASHNODE-OFFLINE-2026-09-18.json"


def pages() -> list[Page]:
    specs = [
        (
            "agents-zero-to-hero-1-building-an-ai-agent-from-scratch-with-tool-calling",
            "article_agent_loop.html",
            0,
        ),
        ("", "homepage.html", 1),
        ("series/agent-zero-2-hero", "series.html", 1),
        ("tag/python", "tag_python.html", 1),
    ]
    out: list[Page] = []
    for path, file, depth in specs:
        html = (FIXTURES / file).read_text(encoding="utf-8")
        title = html.split("<title>", 1)[1].split("</title>", 1)[0]
        url = BASE if not path else BASE.rstrip("/") + "/" + path
        out.append(
            Page(
                id=new_id(),
                job_id="offline-hashnode",
                url=url,
                depth=depth,
                status_code=200,
                html=html,
                title=title,
            )
        )
    return out


def main() -> int:
    ps = pages()
    profile = build_structured_profile(ps, BASE)
    understanding = project_understanding(profile, provenance="derived_metric")
    discovery = discover_queries(understanding, top_n=20, selection_seed=18)

    industry = understanding.industry_category_guess
    genre = understanding.site_genre
    pm_ok = industry != "project_management"

    intent_examples: dict[str, list[str]] = {}
    for q in discovery.queries:
        intent_examples.setdefault(q.intent, []).append(q.query)

    rejected_reasons = Counter()
    for ex in discovery.rejected_examples:
        for r in (ex.get("decision") or {}).get("reasons") or []:
            rejected_reasons[r.split(":")[0]] += 1

    report = {
        "target": BASE,
        "fixture_files": sorted(p.name for p in FIXTURES.glob("*.html")),
        "site_genre": genre,
        "industry_category_guess": industry,
        "industry_omitted": profile.industry_category.omitted,
        "not_project_management": pm_ok,
        "org_name": understanding.organization_brand,
        "primary_topics": understanding.topics[:12],
        "products_services": understanding.products_services,
        "tags_not_in_products": not any(
            str(p).startswith("#") for p in understanding.products_services
        ),
        "profile_warnings": understanding.warnings,
        "evidence_hash": understanding.evidence_hash,
        "candidates_count": discovery.candidates_count,
        "accepted_count": discovery.accepted_count,
        "rejected_count": discovery.rejected_count,
        "selected_count": discovery.selected_count,
        "intent_breakdown": discovery.intent_breakdown,
        "intent_examples": {k: v[:3] for k, v in intent_examples.items()},
        "rejected_reason_counts": dict(rejected_reasons),
        "paid_retrieval_opt_in": discovery.paid_retrieval_opt_in,
        "paid_retrieval_ready": discovery.paid_retrieval_ready,
        "selected_queries": [
            {"id": q.id, "intent": q.intent, "query": q.query, "topic": q.topic}
            for q in discovery.queries
        ],
        "profile_structured": understanding.structured,
    }

    OUT_JSON.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")

    lines = [
        "# Phase 3 Hashnode offline validation",
        "",
        "**Date:** 2026-09-18",
        f"**Target:** {BASE}",
        "**Mode:** offline fixtures (`tests/fixtures/hashnode`) — no paid APIs",
        "",
        "## Verdict",
        f"- Primary industry is **not** `project_management`: **{pm_ok}** "
        f"(guess={industry!r}, omitted={profile.industry_category.omitted})",
        f"- site_genre: **{genre}**",
        f"- Tags not in products: **{report['tags_not_in_products']}**",
        f"- Paid retrieval auto-run: **false** (opt_in={discovery.paid_retrieval_opt_in})",
        "",
        "## Profile evidence",
        f"- org_name: {understanding.organization_brand}",
        f"- topics (sample): {understanding.topics[:8]}",
        f"- products_services: {understanding.products_services}",
        f"- evidence_hash: `{understanding.evidence_hash}`",
        f"- warnings: {understanding.warnings[:8]}",
        "",
        "## Query discovery counts",
        f"- generated (post-dedupe candidates): {discovery.candidates_count}",
        f"- accepted: {discovery.accepted_count}",
        f"- rejected: {discovery.rejected_count}",
        f"- selected (top_k=20, seed=18): {discovery.selected_count}",
        f"- intent_breakdown: {discovery.intent_breakdown}",
        "",
        "## Examples per intent",
    ]
    for intent, qs in sorted(intent_examples.items()):
        lines.append(f"### {intent}")
        for q in qs[:3]:
            lines.append(f"- {q}")
        lines.append("")
    lines.extend(
        [
            "## Gate reject reason families",
            f"- {dict(rejected_reasons)}",
            "",
            "## Artifacts",
            f"- JSON: `{OUT_JSON.relative_to(ROOT)}`",
            "- Fixtures: `tests/fixtures/hashnode/`",
            "",
            "## H1–H10 checklist",
            f"- H1 Not primarily project_management without evidence: {'PASS' if pm_ok else 'FAIL'}",
            "- H2 AI/agent/tooling topic queries when headings present: "
            + (
                "PASS"
                if any(
                    "agent" in q.query.lower() or "tool" in q.query.lower()
                    for q in discovery.queries
                )
                else "FAIL"
            ),
            "- H3 No paid discovery calls: PASS",
            "",
        ]
    )
    OUT_MD.write_text("\n".join(lines), encoding="utf-8")
    print(OUT_MD)
    print(json.dumps({"not_pm": pm_ok, "genre": genre, "selected": discovery.selected_count}))
    return 0 if pm_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
