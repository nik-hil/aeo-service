"""Tests for Hashnode .md alternate content representation (mocked HTTP)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.orm import Session

from aeo_mvp.analyzers.base import eligible_pages
from aeo_mvp.analyzers.content import analyze_content
from aeo_mvp.crawler.alternate import (
    get_supported_alternate_url,
    is_primary_blocked,
    is_primary_usable,
)
from aeo_mvp.crawler.discover import crawl_live, extract_links
from aeo_mvp.crawler.fetch import FetchResult
from aeo_mvp.crawler.markdown_normalize import markdown_to_analyzable_html
from aeo_mvp.crawler.page_fetch import fetch_page_with_alternate
from aeo_mvp.db.models import Job, new_id
from aeo_mvp.pipeline.orchestrator import create_job_record


HASHNODE_ARTICLE = (
    "https://nik-hil.hashnode.dev/agents-zero-to-hero-1-building-an-ai-agent"
)
HASHNODE_MD = HASHNODE_ARTICLE + ".md"
HASHNODE_SERIES = "https://nik-hil.hashnode.dev/series/agent-zero-2-hero"
CF_BODY = "<html><title>Just a moment...</title><body>cf-browser-verification</body></html>"
ARTICLE_HTML = (
    "<html><head><title>AI Agent Guide</title></head>"
    "<body><h1>AI Agent Guide</h1><p>Build agents with tools. "
    '<a href="/other-post">Other</a></p></body></html>'
)
ARTICLE_MD = """# AI Agent Guide

Build agents with tools and careful permissions.

## Why it matters

Answer engines prefer clear definitions.
"""


def _resp(status: int, text: str, content_type: str = "text/html") -> MagicMock:
    r = MagicMock()
    r.status_code = status
    r.headers = {"content-type": content_type}
    r.text = text
    return r


# ---------------------------------------------------------------------------
# Alternate URL helper
# ---------------------------------------------------------------------------


def test_hashnode_article_gets_md_alternate():
    alt = get_supported_alternate_url(HASHNODE_ARTICLE)
    assert alt is not None
    assert alt.url == HASHNODE_MD
    assert alt.representation == "markdown"
    assert alt.adapter == "hashnode"


def test_hashnode_series_no_md():
    assert get_supported_alternate_url(HASHNODE_SERIES) is None


def test_non_hashnode_no_md():
    assert get_supported_alternate_url("https://example.com/my-post") is None
    assert get_supported_alternate_url("https://hashnode.dev/blog") is None


def test_already_md_no_double_extension():
    assert get_supported_alternate_url(HASHNODE_MD) is None


def test_hashnode_tag_and_homepage_no_md():
    assert get_supported_alternate_url("https://nik-hil.hashnode.dev/") is None
    assert get_supported_alternate_url("https://nik-hil.hashnode.dev/tag/python") is None


def test_blocked_detection_403_and_cf_body():
    assert is_primary_blocked(status_code=403)
    assert is_primary_blocked(status_code=200, text=CF_BODY)
    assert not is_primary_blocked(status_code=404)
    assert is_primary_usable(status_code=200, text=ARTICLE_HTML)
    assert not is_primary_usable(status_code=200, text=CF_BODY)


# ---------------------------------------------------------------------------
# Fetch orchestration (mocked)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_html_success_does_not_attempt_alternate(monkeypatch):
    calls: list[str] = []

    async def fake_fetch(client, url, *, timeout_s=5.0):  # noqa: ANN001
        calls.append(url)
        return FetchResult(
            url=url,
            final_url=url,
            status_code=200,
            content_type="text/html",
            text=ARTICLE_HTML,
            error=None,
        )

    monkeypatch.setattr("aeo_mvp.crawler.page_fetch.fetch_url", fake_fetch)
    client = MagicMock()
    out = await fetch_page_with_alternate(client, HASHNODE_ARTICLE)
    assert calls == [HASHNODE_ARTICLE]
    assert out.representation == "html"
    assert out.alternate_fetch_status == "not_attempted"
    assert out.primary_fetch_status == "success"
    assert out.html_discovery_ok is True


@pytest.mark.asyncio
async def test_hashnode_403_attempts_md(monkeypatch):
    calls: list[str] = []

    async def fake_fetch(client, url, *, timeout_s=5.0):  # noqa: ANN001
        calls.append(url)
        if url.endswith(".md"):
            return FetchResult(
                url=url,
                final_url=url,
                status_code=200,
                content_type="text/markdown",
                text=ARTICLE_MD,
                error=None,
            )
        return FetchResult(
            url=url,
            final_url=url,
            status_code=403,
            content_type="text/html",
            text=CF_BODY,
            error=None,
        )

    monkeypatch.setattr("aeo_mvp.crawler.page_fetch.fetch_url", fake_fetch)
    out = await fetch_page_with_alternate(MagicMock(), HASHNODE_ARTICLE)
    assert calls == [HASHNODE_ARTICLE, HASHNODE_MD]
    assert out.primary_fetch_status == "blocked"
    assert out.alternate_fetch_status == "success"
    assert out.representation == "markdown"
    assert out.canonical_url == HASHNODE_ARTICLE
    assert out.source_url == HASHNODE_MD
    assert out.html and "<h1>" in out.html
    assert out.fetch_error is None
    assert out.html_discovery_ok is False


@pytest.mark.asyncio
async def test_403_md_fail_both_diagnosable(monkeypatch):
    async def fake_fetch(client, url, *, timeout_s=5.0):  # noqa: ANN001
        if url.endswith(".md"):
            return FetchResult(
                url=url,
                final_url=url,
                status_code=404,
                content_type="text/html",
                text="missing",
                error=None,
            )
        return FetchResult(
            url=url,
            final_url=url,
            status_code=403,
            content_type="text/html",
            text=CF_BODY,
            error=None,
        )

    monkeypatch.setattr("aeo_mvp.crawler.page_fetch.fetch_url", fake_fetch)
    out = await fetch_page_with_alternate(MagicMock(), HASHNODE_ARTICLE)
    assert out.html is None
    assert out.alternate_fetch_status == "failed"
    assert out.primary_fetch_status == "blocked"
    assert out.fetch_error is not None
    assert "primary_unavailable" in out.fetch_error
    assert "alternate_failed" in out.fetch_error
    assert "403" in out.fetch_error
    assert "404" in out.fetch_error


@pytest.mark.asyncio
async def test_alternate_still_goes_through_ssrf(monkeypatch):
    """Alternate URL must be fetched via fetch_url (SSRF path), not a raw client.get."""

    async def fake_fetch(client, url, *, timeout_s=5.0):  # noqa: ANN001
        if url.endswith(".md"):
            raise AssertionError("should be blocked before connect in this test")
        return FetchResult(
            url=url,
            final_url=url,
            status_code=403,
            content_type="text/html",
            text=CF_BODY,
            error=None,
        )

    async def ssrf_fetch(client, url, *, timeout_s=5.0):  # noqa: ANN001
        if url.endswith(".md"):
            return FetchResult(
                url=url,
                final_url=url,
                status_code=None,
                content_type=None,
                text=None,
                error="ssrf_blocked: private address",
            )
        return await fake_fetch(client, url, timeout_s=timeout_s)

    monkeypatch.setattr("aeo_mvp.crawler.page_fetch.fetch_url", ssrf_fetch)
    out = await fetch_page_with_alternate(MagicMock(), HASHNODE_ARTICLE)
    assert out.alternate_fetch_status == "failed"
    assert out.fetch_error and "ssrf" in out.fetch_error.lower()


@pytest.mark.asyncio
async def test_non_hashnode_403_does_not_invent_md(monkeypatch):
    calls: list[str] = []

    async def fake_fetch(client, url, *, timeout_s=5.0):  # noqa: ANN001
        calls.append(url)
        return FetchResult(
            url=url,
            final_url=url,
            status_code=403,
            content_type="text/html",
            text=CF_BODY,
            error=None,
        )

    monkeypatch.setattr("aeo_mvp.crawler.page_fetch.fetch_url", fake_fetch)
    url = "https://example.com/post"
    out = await fetch_page_with_alternate(MagicMock(), url)
    assert calls == [url]
    assert out.alternate_fetch_status == "not_applicable"
    assert out.html is None


# ---------------------------------------------------------------------------
# Crawl integration + eligibility + pipeline
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_crawl_403_md_success_eligible_and_provenance(db_session: Session, monkeypatch):
    async def fake_fetch(client, url, *, timeout_s=5.0):  # noqa: ANN001
        if "robots.txt" in url:
            return FetchResult(
                url=url,
                final_url=url,
                status_code=404,
                content_type="text/plain",
                text=None,
                error=None,
            )
        if url.endswith(".md"):
            return FetchResult(
                url=url,
                final_url=url,
                status_code=200,
                content_type="text/markdown",
                text=ARTICLE_MD,
                error=None,
            )
        return FetchResult(
            url=url,
            final_url=url,
            status_code=403,
            content_type="text/html",
            text=CF_BODY,
            error=None,
        )

    monkeypatch.setattr("aeo_mvp.crawler.page_fetch.fetch_url", fake_fetch)
    monkeypatch.setattr("aeo_mvp.crawler.discover.fetch_url", fake_fetch)
    monkeypatch.setattr(
        "aeo_mvp.crawler.discover.assert_safe_public_url",
        lambda u: u,
    )

    job = create_job_record(db_session, HASHNODE_ARTICLE, demo_mode=False, options={})
    db_session.commit()

    outcome = await crawl_live(
        db_session,
        job.id,
        HASHNODE_ARTICLE,
        max_pages=1,
        max_depth=0,
        timeout_s=1.0,
    )
    assert outcome.crawl_status in {"ok", "degraded"}
    assert outcome.fetched >= 1
    pages = eligible_pages(outcome.pages)
    assert len(pages) == 1
    p = pages[0]
    assert p.url == HASHNODE_ARTICLE or p.url.rstrip("/") == HASHNODE_ARTICLE.rstrip("/")
    assert p.source_url == HASHNODE_MD
    assert p.content_representation == "markdown"
    assert p.primary_status_code == 403
    assert p.primary_fetch_status == "blocked"
    assert p.alternate_fetch_status == "success"
    assert p.status_code == 200
    assert p.fetch_error is None
    assert p.html and "AI Agent Guide" in p.html
    assert p.source_markdown == ARTICLE_MD
    assert p.title == "AI Agent Guide"
    assert p.canonical_url == HASHNODE_ARTICLE or (
        p.canonical_url and p.canonical_url.rstrip("/") == HASHNODE_ARTICLE.rstrip("/")
    )


@pytest.mark.asyncio
async def test_markdown_reaches_existing_content_analyzer(db_session: Session):
    """Normalized markdown HTML is scored by the same analyze_content path."""
    job = Job(id=new_id(), base_url=HASHNODE_ARTICLE, demo_mode=0, status="analyzing")
    db_session.add(job)
    db_session.flush()
    normalized = markdown_to_analyzable_html(ARTICLE_MD)
    from aeo_mvp.db.models import Page

    page = Page(
        id=new_id(),
        job_id=job.id,
        url=HASHNODE_ARTICLE,
        final_url=HASHNODE_MD,
        source_url=HASHNODE_MD,
        content_representation="markdown",
        depth=0,
        status_code=200,
        primary_status_code=403,
        primary_fetch_status="blocked",
        alternate_fetch_status="success",
        content_type="text/markdown",
        html=normalized.html,
        title=normalized.title,
        fetch_error=None,
    )
    db_session.add(page)
    db_session.flush()
    result = analyze_content(db_session, job.id, [page], provenance="derived_metric")
    assert result.content_score >= 0
    assert eligible_pages([page]) == [page]


@pytest.mark.asyncio
async def test_html_discovery_not_driven_by_markdown_links(db_session: Session, monkeypatch):
    """When only .md succeeds, do not enqueue Markdown-derived links."""

    md_with_link = ARTICLE_MD + "\n\nSee [Other](https://nik-hil.hashnode.dev/other-post).\n"
    fetched_urls: list[str] = []

    async def fake_fetch(client, url, *, timeout_s=5.0):  # noqa: ANN001
        fetched_urls.append(url)
        if "robots.txt" in url:
            return FetchResult(
                url=url, final_url=url, status_code=404, content_type="text/plain", text=None
            )
        if url.endswith(".md"):
            return FetchResult(
                url=url,
                final_url=url,
                status_code=200,
                content_type="text/markdown",
                text=md_with_link,
                error=None,
            )
        return FetchResult(
            url=url,
            final_url=url,
            status_code=403,
            content_type="text/html",
            text=CF_BODY,
            error=None,
        )

    monkeypatch.setattr("aeo_mvp.crawler.page_fetch.fetch_url", fake_fetch)
    monkeypatch.setattr("aeo_mvp.crawler.discover.fetch_url", fake_fetch)
    monkeypatch.setattr("aeo_mvp.crawler.discover.assert_safe_public_url", lambda u: u)

    job = create_job_record(db_session, HASHNODE_ARTICLE, demo_mode=False, options={})
    db_session.commit()
    outcome = await crawl_live(
        db_session,
        job.id,
        HASHNODE_ARTICLE,
        max_pages=5,
        max_depth=2,
        timeout_s=1.0,
    )
    page_urls = {p.url for p in outcome.pages}
    assert not any("other-post" in u for u in page_urls)
    assert not any(u.endswith("/other-post") for u in fetched_urls)


def test_extract_links_still_works_on_html():
    links = extract_links(ARTICLE_HTML, "https://nik-hil.hashnode.dev/agents-zero-to-hero-1")
    assert any(l.endswith("/other-post") for l in links)


def test_markdown_normalize_structure():
    n = markdown_to_analyzable_html(ARTICLE_MD)
    assert n.title == "AI Agent Guide"
    assert "<h1>" in n.html and "<h2>" in n.html
    assert "<p>" in n.html


# ---------------------------------------------------------------------------
# Direct .md URL (first-class Markdown representation)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_direct_md_url_is_markdown_not_html(monkeypatch):
    """Regression: .md URL with text/markdown 200 must not be treated as HTML."""
    md_url = "https://example.hashnode.dev/my-article.md"
    body = "# My Article\n\nHello from Hashnode Markdown.\n"
    calls: list[str] = []

    async def fake_fetch(client, url, *, timeout_s=5.0):  # noqa: ANN001
        calls.append(url)
        return FetchResult(
            url=url,
            final_url=url,
            status_code=200,
            content_type="text/markdown",
            text=body,
            error=None,
        )

    monkeypatch.setattr("aeo_mvp.crawler.page_fetch.fetch_url", fake_fetch)
    out = await fetch_page_with_alternate(MagicMock(), md_url)
    assert calls == [md_url]
    assert out.representation == "markdown"
    assert out.title == "My Article"
    assert out.source_url == md_url
    assert out.canonical_url == "https://example.hashnode.dev/my-article"
    assert out.source_markdown == body
    assert out.html and "<h1>" in out.html
    assert out.html_discovery_ok is False
    # Never invent a .md.md twin request.
    assert not any(u.endswith(".md.md") for u in calls)


@pytest.mark.asyncio
async def test_direct_md_never_requests_md_md(monkeypatch):
    from aeo_mvp.crawler.alternate import get_supported_alternate_url, strip_one_md_suffix

    md_url = HASHNODE_MD
    assert get_supported_alternate_url(md_url) is None
    assert strip_one_md_suffix(md_url) == HASHNODE_ARTICLE
    assert strip_one_md_suffix(md_url + ".md").endswith(".md")  # only one strip

    async def fake_fetch(client, url, *, timeout_s=5.0):  # noqa: ANN001
        assert not url.endswith(".md.md")
        return FetchResult(
            url=url,
            final_url=url,
            status_code=200,
            content_type="text/markdown",
            text=ARTICLE_MD,
            error=None,
        )

    monkeypatch.setattr("aeo_mvp.crawler.page_fetch.fetch_url", fake_fetch)
    out = await fetch_page_with_alternate(MagicMock(), md_url)
    assert out.canonical_url == HASHNODE_ARTICLE
    assert out.source_markdown == ARTICLE_MD


@pytest.mark.asyncio
async def test_html_success_source_markdown_is_none(monkeypatch):
    async def fake_fetch(client, url, *, timeout_s=5.0):  # noqa: ANN001
        return FetchResult(
            url=url,
            final_url=url,
            status_code=200,
            content_type="text/html",
            text=ARTICLE_HTML,
            error=None,
        )

    monkeypatch.setattr("aeo_mvp.crawler.page_fetch.fetch_url", fake_fetch)
    out = await fetch_page_with_alternate(MagicMock(), HASHNODE_ARTICLE)
    assert out.representation == "html"
    assert out.source_markdown is None


def test_markdown_path_does_not_fabricate_jsonld_meta_robots():
    n = markdown_to_analyzable_html(ARTICLE_MD)
    assert "application/ld+json" not in n.html
    assert 'name="robots"' not in n.html
    assert 'rel="canonical"' not in n.html
