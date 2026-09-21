"""Minimal report fixtures for Gradio UI adapter tests."""

from __future__ import annotations

SAMPLE_REPORT = {
    "job_id": "job-demo-1",
    "base_url": "https://demo.example/",
    "demo_mode": True,
    "status": "completed",
    "pages_crawled": 5,
    "caveats": ["Visibility metrics are sample estimates, not rankings."],
    "scores": {
        "aeo_health": {"value": 87.9, "provenance": "derived_metric", "formula_version": "health-v1"},
        "technical": {"value": 100.0, "provenance": "derived_metric"},
        "content": {"value": 57.5, "provenance": "derived_metric"},
        "entity": {"value": 92.5, "provenance": "derived_metric"},
        "structured_data": {"value": 100.0, "provenance": "derived_metric"},
        "answerability": {"value": 100.0, "provenance": "derived_metric"},
    },
    "experiment": {
        "provider_name": "demo",
        "experiment_kind": "llm_mention",
        "measures_consumer_ui": False,
        "llm_mention_rate": {"value": 0.4, "provenance": "synthetic_demo"},
        "query_coverage": {"value": 0.6, "provenance": "synthetic_demo"},
    },
    "executive_summary": {
        "strongest_areas": ["technical", "structured_data"],
        "weakest_areas": ["content"],
        "top_3_actions": ["Improve answer-first intros", "Expand FAQ"],
    },
    "crawl": {"status": "completed", "discovered": 5, "fetched": 5, "errors": 0},
    "page_intelligence": {
        "url": "https://demo.example/",
        "title": "AcmeFlow — Demo",
        "meta_description": "Demo homepage",
        "heading_outline": ["Welcome", "Features"],
        "answer_blocks": [{"kind": "definition", "text": "AcmeFlow helps teams."}],
        "word_count": 420,
    },
    "recommendations": [
        {
            "id": "r2",
            "code": "CONTENT_ANSWER_FIRST",
            "title": "Add answer-first intro",
            "rank": 2,
            "priority_score": 7.0,
            "effort": "M",
            "impact": 10,
            "problem": "Intro is vague",
            "why_it_matters": "Answer engines prefer direct answers",
            "recommended_action": "Lead with a 40+ char declarative sentence",
            "affected_urls": ["https://demo.example/"],
            "evidence_snippets": ["First paragraph is navigational"],
        },
        {
            "id": "r1",
            "code": "SCHEMA_ORG",
            "title": "Add Organization schema",
            "rank": 1,
            "priority_score": 8.0,
            "effort": "S",
            "impact": 8,
            "problem": "Missing Organization JSON-LD on about",
            "why_it_matters": "Entity clarity",
            "recommended_action": "Add Organization schema",
            "affected_urls": ["https://demo.example/about"],
            "evidence_snippets": ["No @type Organization"],
        },
    ],
    "content_gaps": [
        {
            "page_url": "https://demo.example/pricing",
            "gaps": [
                {
                    "gap_id": "g1",
                    "gap_type": "thin_coverage",
                    "severity": "high",
                    "rationale": "Pricing page lacks FAQ answers",
                    "best_page_url": "https://demo.example/pricing",
                },
                {
                    "gap_id": "g2",
                    "gap_type": "schema_gap",
                    "severity": "low",
                    "rationale": "Low severity ignored for opportunities",
                },
            ],
        }
    ],
    "optimization_briefs": [
        {
            "brief_id": "b1",
            "page_url": "https://demo.example/",
            "action": "expand_section",
            "proposed_title": "AcmeFlow",
            "executive_summary": "Expand homepage answer block",
            "outline": ["Intro", "FAQ"],
            "work_queue": [
                {"action": "add", "target": "section:FAQ", "reason": "Missing FAQ"},
            ],
            "caveats": ["Brief is not a published page"],
            "provenance_notes": ["Grounded in page_intelligence"],
        }
    ],
    "content_drafts": [
        {
            "page_url": "https://demo.example/",
            "status": "generated",
            "generator": "deterministic_skeleton",
            "content_provenance": "generated",
            "disclaimer": "Draft suggestion only — not published; not a guarantee of AI citation.",
            "body_markdown": "# AcmeFlow\n\n*(Skeleton)* Answer the pricing question.\n",
        }
    ],
    "page_findings": [
        {
            "url": "https://demo.example/",
            "title": "Home",
            "issue_count": 1,
            "issues": [{"code": "CONTENT_ANSWER_FIRST", "summary": "Weak intro"}],
        }
    ],
}

PARTIAL_CRAWL_REPORT = {
    **SAMPLE_REPORT,
    "job_id": "job-partial",
    "crawl": {"status": "partial", "discovered": 10, "fetched": 4, "errors": 2},
    "pages_crawled": 4,
}

MALFORMED_REPORT = {
    "job_id": "job-bad",
    "scores": "not-a-dict",
    "recommendations": [None, "x", {"title": "Only title"}],
    "content_gaps": "nope",
}

PAGES_PAYLOAD = {
    "job_id": "job-demo-1",
    "count": 2,
    "pages": [
        {
            "id": "p1",
            "url": "https://demo.example/",
            "title": "Home",
            "depth": 0,
            "status_code": 200,
            "fetch_error": None,
        },
        {
            "id": "p2",
            "url": "https://demo.example/about",
            "title": "About",
            "depth": 1,
            "status_code": 200,
            "fetch_error": None,
        },
    ],
}

# SYNTHETIC — for UI table/pagination tests only; not a live crawl fixture.
SYNTHETIC_20_PAGES = {
    "job_id": "job-synthetic-20",
    "count": 20,
    "synthetic": True,
    "pages": [
        {
            "id": f"sp{i}",
            "url": f"https://demo.example/section/path/page-{i:02d}/very/long/slug/for-truncation-testing",
            "title": f"Synthetic page {i}",
            "depth": 0 if i == 1 else (1 if i < 10 else 2),
            "status_code": 200 if i % 7 else 404,
            "fetch_error": None if i % 7 else "not found",
        }
        for i in range(1, 21)
    ],
}

XSS_PAYLOAD = '<script>alert("xss")</script><img src=x onerror=alert(1)>'

OPT_PAYLOAD_ABOUT = {
    "page_intelligence": {
        "url": "https://demo.example/about",
        "title": "About AcmeFlow",
        "meta_description": "About page",
        "heading_outline": ["About", "Team"],
        "answer_blocks": [{"kind": "definition", "text": "AcmeFlow is a demo."}],
        "word_count": 180,
    },
    "content_gaps": [
        {
            "page_url": "https://demo.example/about",
            "gaps": [
                {
                    "gap_id": "g-about",
                    "gap_type": "entity_gap",
                    "severity": "medium",
                    "rationale": "About page lacks sameAs links",
                }
            ],
        }
    ],
    "optimization_briefs": [
        {
            "brief_id": "b-about",
            "page_url": "https://demo.example/about",
            "action": "add_entity_markup",
            "proposed_title": "About AcmeFlow",
            "executive_summary": "Add Organization schema on About",
            "outline": ["Intro", "Team", "Contact"],
            "work_queue": [],
            "caveats": [],
            "provenance_notes": ["Enriched via content-optimization"],
        }
    ],
    "content_drafts": [
        {
            "page_url": "https://demo.example/about",
            "status": "generated",
            "generator": "deterministic_skeleton",
            "content_provenance": "generated",
            "disclaimer": "Draft suggestion only",
            "body_markdown": "# About AcmeFlow\n\n*(Skeleton)*\n",
        }
    ],
}
