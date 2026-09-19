"""Workstream D — P1-7 OpenAPI contract + P1-15 prompt_set_id honesty.

No live DO / Hashnode. Preserves P0s + A+B+C.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest
import yaml

from aeo_mvp.api.schemas import ContentOptimizationRequest, JobOptions
from aeo_mvp.config import PROMPT_SET_ID
from aeo_mvp.content.models import ContentOptimizationResult
from aeo_mvp.content.page_intel import extract_page_intelligence
from aeo_mvp.crawler.discover import crawl_demo
from aeo_mvp.db.models import ExperimentConfig, Job
from aeo_mvp.pipeline.orchestrator import JobOrchestrator, create_job_record
from aeo_mvp.queries.discovery import DiscoveryResult, DiscoveredQuery
from aeo_mvp.queries.select import QUERY_SET_VERSION as QUERY_SET_V2
from aeo_mvp.queries.select_v2 import QUERY_SET_VERSION as QUERY_SET_V3


async def _fake_crawl(session, job_id, base_url, **kwargs):
    return crawl_demo(session, job_id)

OPENAPI_PATH = (
    Path(__file__).resolve().parents[2] / "docs" / "api" / "openapi-sketch.yaml"
)


def _load_openapi() -> dict:
    return yaml.safe_load(OPENAPI_PATH.read_text(encoding="utf-8"))


# --- P1-7: OpenAPI ↔ live wire ---------------------------------------------


def test_p1_7_openapi_job_options_providers_and_flags():
    spec = _load_openapi()
    props = spec["components"]["schemas"]["JobOptions"]["properties"]
    enum = props["provider"]["enum"]
    assert "digitalocean_web_search" in enum
    assert "digitalocean" in enum
    assert "openai_compatible" in enum
    assert "auto" in enum
    assert "demo" in enum

    for key in (
        "content_optimization",
        "content_draft",
        "generate_draft",
        "draft_paid",
        "paid_retrieval_opt_in",
        "query_discovery_version",
        "discovery_only",
        "dry_run",
    ):
        assert key in props, f"JobOptions missing {key} in OpenAPI"

    live = JobOptions.model_fields
    for key in (
        "content_optimization",
        "paid_retrieval_opt_in",
        "generate_draft",
        "draft_paid",
        "provider",
    ):
        assert key in live
        assert key in props


def test_p1_7_openapi_content_optimization_plurals_authoritative():
    spec = _load_openapi()
    resp = spec["components"]["schemas"]["ContentOptimizationResponse"]
    required = set(resp["required"])
    assert required >= {
        "page_intelligence",
        "content_gaps",
        "optimization_briefs",
        "content_drafts",
    }
    # Singular must not be required
    assert "gap_report" not in required
    assert "brief" not in required
    assert "draft" not in required

    props = resp["properties"]
    for singular in ("gap_report", "brief", "draft"):
        assert props[singular].get("deprecated") is True
        assert props[singular].get("x-deprecated") is True

    page = extract_page_intelligence(
        "<html><body><h1>Acme</h1><p>Acme builds widgets for teams.</p></body></html>",
        url="https://acme.example/",
    )
    from aeo_mvp.content.brief import build_optimization_brief
    from aeo_mvp.content.draft import build_optimized_draft
    from aeo_mvp.content.gaps import build_content_gap_report

    qs = {
        "query_set_version": QUERY_SET_V3,
        "members": [
            {
                "query_id": "q1",
                "query": "What is Acme?",
                "intent": "informational",
                "topic": None,
            }
        ],
    }
    gap = build_content_gap_report(page, qs)
    brief = build_optimization_brief(page, gap)
    draft = build_optimized_draft(page, brief, gap)
    result = ContentOptimizationResult(
        page_intelligence=page,
        gap_report=gap,
        brief=brief,
        draft=draft,
    )
    wire = result.to_dict()
    for key in ("content_gaps", "optimization_briefs", "content_drafts"):
        assert key in wire and isinstance(wire[key], list)
    for key in ("gap_report", "brief", "draft"):
        assert key in wire  # compat aliases still present


def test_p1_7_openapi_auth_and_error_shape():
    spec = _load_openapi()
    assert "bearerAuth" in spec["components"]["securitySchemes"]
    assert spec["security"] == [{"bearerAuth": []}]
    health = spec["paths"]["/health"]["get"]
    assert health.get("security") == []

    jobs_post = spec["paths"]["/api/v1/jobs"]["post"]["responses"]
    assert "401" in jobs_post
    opt = spec["paths"]["/api/v1/content-optimization"]["post"]["responses"]
    for code in ("400", "401", "409", "422"):
        assert code in opt

    err = spec["components"]["schemas"]["ErrorResponse"]
    assert "detail" in err["required"]


def test_p1_7_drift_job_options_fields_documented():
    """Drift guard: every documented JobOptions field exists on live model."""
    spec = _load_openapi()
    documented = set(spec["components"]["schemas"]["JobOptions"]["properties"])
    live = set(JobOptions.model_fields)
    # Sketch may omit obscure extras; required live contract fields must be present.
    must = {
        "max_pages",
        "max_depth",
        "runs_per_prompt",
        "provider",
        "content_optimization",
        "content_draft",
        "generate_draft",
        "draft_paid",
        "paid_retrieval_opt_in",
        "query_discovery_version",
        "discovery_only",
        "dry_run",
    }
    assert must <= documented
    assert must <= live


def test_p1_7_drift_content_opt_request_flags():
    spec = _load_openapi()
    props = spec["components"]["schemas"]["ContentOptimizationRequest"]["properties"]
    live = set(ContentOptimizationRequest.model_fields)
    for key in (
        "content_optimization",
        "generate_draft",
        "draft_paid",
        "paid_llm_opt_in",
        "allow_empty_html",
    ):
        assert key in props
        assert key in live


# --- P1-15: prompt_set_id from query_set_version -----------------------------


def test_p1_15_build_prompts_stamps_query_set_version():
    orch = JobOrchestrator.__new__(JobOrchestrator)
    job = Job(
        id="j1",
        base_url="https://acme.example/",
        status="pending",
        demo_mode=0,
        options_json="{}",
        created_at="2026-01-01T00:00:00Z",
        updated_at="2026-01-01T00:00:00Z",
    )
    discovered = [{"id": "q1", "query": "What is Acme?", "intent": "informational"}]
    prompts, psid = orch._build_prompts(
        job,
        {},
        "Acme",
        discovered=discovered,
        prompt_set_id=QUERY_SET_V3,
    )
    assert prompts == discovered
    assert psid == QUERY_SET_V3
    assert psid != "discovered-queries-v1"


def test_p1_15_build_prompts_requires_prompt_set_id_when_discovered():
    orch = JobOrchestrator.__new__(JobOrchestrator)
    job = Job(
        id="j1",
        base_url="https://acme.example/",
        status="pending",
        demo_mode=0,
        options_json="{}",
        created_at="2026-01-01T00:00:00Z",
        updated_at="2026-01-01T00:00:00Z",
    )
    with pytest.raises(ValueError, match="query_set_version"):
        orch._build_prompts(
            job,
            {},
            "Acme",
            discovered=[{"id": "q1", "query": "x", "intent": "informational"}],
        )


def test_p1_15_prompt_set_id_from_discovery_prefers_query_set_version():
    d = DiscoveryResult(
        queries=[],
        query_set_version=QUERY_SET_V3,
        method="query-discovery-v2",
        query_set={"query_set_version": "should-not-win"},
    )
    assert JobOrchestrator._prompt_set_id_from_discovery(d) == QUERY_SET_V3

    d_v1 = DiscoveryResult(
        queries=[],
        query_set_version=QUERY_SET_V2,
        method="query-discovery-v1",
    )
    assert JobOrchestrator._prompt_set_id_from_discovery(d_v1) == QUERY_SET_V2

    # Nested fallback when top-level empty
    nested = SimpleNamespace(
        query_set_version="",
        query_set={"query_set_version": QUERY_SET_V3},
        method="query-discovery-v2",
    )
    assert JobOrchestrator._prompt_set_id_from_discovery(nested) == QUERY_SET_V3


def test_p1_15_v2_discovery_job_stamps_query_set_v3(db_session):
    """End-to-end: default v2 discovery → ExperimentConfig.prompt_set_id == query-set-v3."""
    discovery = DiscoveryResult(
        queries=[
            DiscoveredQuery(
                id="dq1",
                query="What is AcmeFlow?",
                classification="brand",
                intent="navigational",
            ),
            DiscoveredQuery(
                id="dq2",
                query="How does AcmeFlow help teams?",
                classification="informational",
                intent="informational",
            ),
        ],
        selected_count=2,
        accepted_count=2,
        fallback_used=False,
        method="query-discovery-v2",
        query_set_version=QUERY_SET_V3,
        query_set={"query_set_version": QUERY_SET_V3, "status": "ready"},
        paid_retrieval_ready=False,
        fingerprint="fp-test-p1-15",
    )

    job = create_job_record(
        db_session,
        "https://demo.example/",
        demo_mode=False,
        options={
            "provider": "demo",
            "runs_per_prompt": 1,
            "content_optimization": False,
            "query_discovery_version": "v2",
        },
    )
    job.demo_mode = 0
    db_session.commit()

    with (
        patch(
            "aeo_mvp.pipeline.orchestrator.crawl_site",
            side_effect=_fake_crawl,
        ),
        patch(
            "aeo_mvp.pipeline.orchestrator.discover_queries",
            return_value=discovery,
        ),
    ):
        asyncio.run(JobOrchestrator(db_session).run(job.id))
    db_session.commit()

    cfg = (
        db_session.query(ExperimentConfig)
        .filter_by(job_id=job.id)
        .one()
    )
    assert cfg.prompt_set_id == QUERY_SET_V3
    assert cfg.prompt_set_id != "discovered-queries-v1"
    assert cfg.prompt_set_id != PROMPT_SET_ID


def test_p1_15_discovery_only_stamps_query_set_version(db_session):
    discovery = DiscoveryResult(
        queries=[
            DiscoveredQuery(
                id="dq1",
                query="What is Acme?",
                classification="brand",
                intent="navigational",
            )
        ],
        selected_count=1,
        fallback_used=False,
        method="query-discovery-v2",
        query_set_version=QUERY_SET_V3,
        discovery_only=True,
    )
    job = create_job_record(
        db_session,
        "https://demo.example/",
        demo_mode=False,
        options={
            "provider": "demo",
            "discovery_only": True,
            "content_optimization": False,
        },
    )
    job.demo_mode = 0
    db_session.commit()

    with (
        patch(
            "aeo_mvp.pipeline.orchestrator.crawl_site",
            side_effect=_fake_crawl,
        ),
        patch(
            "aeo_mvp.pipeline.orchestrator.discover_queries",
            return_value=discovery,
        ),
    ):
        asyncio.run(JobOrchestrator(db_session).run(job.id))
    db_session.commit()

    cfg = db_session.query(ExperimentConfig).filter_by(job_id=job.id).one()
    assert cfg.prompt_set_id == QUERY_SET_V3
    assert cfg.experiment_kind == "discovery_only"
    assert cfg.prompt_set_id != "discovered-queries-dry-run"


def test_p1_15_v1_discovery_stamps_query_set_v2(db_session):
    discovery = DiscoveryResult(
        queries=[
            DiscoveredQuery(
                id="dq1",
                query="What is Acme?",
                classification="brand",
                intent="navigational",
            )
        ],
        selected_count=1,
        fallback_used=False,
        method="query-discovery-v1",
        query_set_version=QUERY_SET_V2,
        query_set={"query_set_version": QUERY_SET_V2},
    )
    job = create_job_record(
        db_session,
        "https://demo.example/",
        demo_mode=False,
        options={
            "provider": "demo",
            "runs_per_prompt": 1,
            "content_optimization": False,
            "query_discovery_version": "v1",
        },
    )
    job.demo_mode = 0
    db_session.commit()

    with (
        patch(
            "aeo_mvp.pipeline.orchestrator.crawl_site",
            side_effect=_fake_crawl,
        ),
        patch(
            "aeo_mvp.pipeline.orchestrator.discover_queries",
            return_value=discovery,
        ),
    ):
        asyncio.run(JobOrchestrator(db_session).run(job.id))
    db_session.commit()

    cfg = db_session.query(ExperimentConfig).filter_by(job_id=job.id).one()
    assert cfg.prompt_set_id == QUERY_SET_V2
