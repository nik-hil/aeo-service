"""Unit tests for AI crawler accessibility analyzer."""

from __future__ import annotations

from aeo_mvp.analyzers.ai_crawlers import (
    AI_CRAWLER_AGENTS,
    CAVEAT,
    analyze_ai_crawlers,
    analyze_path_for_agent,
)
from aeo_mvp.db.models import Job, Page, new_id, utc_now_iso

ROBOTS_FIXTURE = """
User-agent: *
Allow: /

User-agent: GPTBot
Disallow: /

User-agent: OAI-SearchBot
Allow: /

User-agent: Google-Extended
Disallow: /

User-agent: ClaudeBot
Disallow: /pricing

User-agent: PerplexityBot
Allow: /
"""


def test_agents_cover_required_names():
    names = {a["name"] for a in AI_CRAWLER_AGENTS}
    required = {
        "GPTBot",
        "OAI-SearchBot",
        "ChatGPT-User",
        "Google-Extended",
        "Googlebot",
        "ClaudeBot",
        "Claude-SearchBot",
        "Claude-User",
        "PerplexityBot",
        "Perplexity-User",
    }
    assert required <= names


def test_path_policy_from_fixture_robots():
    gpt = analyze_path_for_agent(ROBOTS_FIXTURE, "GPTBot", "/")
    assert gpt.decision == "disallow"
    search = analyze_path_for_agent(ROBOTS_FIXTURE, "OAI-SearchBot", "/")
    assert search.decision == "allow"
    claude_pricing = analyze_path_for_agent(ROBOTS_FIXTURE, "ClaudeBot", "/pricing")
    assert claude_pricing.decision == "disallow"
    claude_home = analyze_path_for_agent(ROBOTS_FIXTURE, "ClaudeBot", "/")
    assert claude_home.decision in ("default_allow", "allow")


def test_analyze_ai_crawlers_persists_and_caveat(db_session):
    job = Job(
        id=new_id(),
        base_url="https://demo.example/",
        demo_mode=1,
        status="analyzing",
        options_json="{}",
        created_at=utc_now_iso(),
        updated_at=utc_now_iso(),
    )
    db_session.add(job)
    page = Page(
        id=new_id(),
        job_id=job.id,
        url="https://demo.example/",
        depth=0,
        status_code=200,
        html="<html><head><title>Demo</title></head><body><p>Hi</p></body></html>",
        title="Demo",
    )
    db_session.add(page)
    db_session.flush()

    result = analyze_ai_crawlers(
        db_session,
        job.id,
        [page],
        robots_raw=ROBOTS_FIXTURE,
        base_url="https://demo.example/",
        provenance="synthetic_demo",
    )
    assert result.robots_fetched is True
    assert len(result.agents) >= 10
    gpt = next(a for a in result.agents if a.crawler_name == "GPTBot")
    assert gpt.purpose == "training"
    assert gpt.source_url
    assert any(pp.decision == "disallow" for pp in gpt.path_policies)
    assert CAVEAT in result.caveat
    assert "allow ⇒" in result.caveat.lower() or "Allow does NOT" in result.caveat
    section = result.report_section
    assert section["caveat"]
    assert len(section["agents"]) >= 10
    # Never claim allow implies visibility in section text
    blob = str(section).lower()
    assert "allow implies visibility" not in blob
