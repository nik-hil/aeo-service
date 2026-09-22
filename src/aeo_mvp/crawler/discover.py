"""Same-host crawl with depth/page caps; demo fixture path."""

from __future__ import annotations

import logging
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timezone
from urllib.parse import urljoin, urlparse, urlunparse

import httpx
from selectolax.parser import HTMLParser
from sqlalchemy.orm import Session

from aeo_mvp.config import USER_AGENT, get_settings
from aeo_mvp.crawler.fetch import default_headers, fetch_url
from aeo_mvp.crawler.page_fetch import fetch_page_with_alternate
from aeo_mvp.crawler.robots import parse_robots, path_from_url
from aeo_mvp.db.models import Page, new_id, utc_now_iso
from aeo_mvp.demo.loader import load_demo_pages, load_demo_robots
from aeo_mvp.security.ssrf import SSRFError, assert_safe_public_url

logger = logging.getLogger(__name__)


@dataclass
class CrawlOutcome:
    pages: list[Page]
    robots_raw: str | None
    robots_allowed_root: float  # T2 pass value
    crawl_status: str = "ok"  # ok | degraded | failed
    discovered: int = 0
    attempted: int = 0
    fetched: int = 0
    errors: int = 0

    def to_dict(self) -> dict[str, int | str]:
        return {
            "status": self.crawl_status,
            "discovered": self.discovered,
            "attempted": self.attempted,
            "fetched": self.fetched,
            "errors": self.errors,
        }


def _summarize_crawl_pages(pages: list[Page], *, discovered: int | None = None) -> dict[str, int | str]:
    """Derive crawl honesty counters from persisted Page rows."""
    from aeo_mvp.analyzers.base import eligible_pages

    attempted = len(pages)
    fetched = len(eligible_pages(pages))
    errors = sum(
        1
        for p in pages
        if p.fetch_error
        or not p.html
        or p.status_code is None
        or not (200 <= (p.status_code or 0) < 300)
    )
    # robots-blocked / fetch_error pages count as errors; avoid double-counting
    # eligible pages that somehow also have error flags (eligible_pages excludes them).
    if fetched == 0:
        status = "failed"
    elif errors > 0:
        status = "degraded"
    else:
        status = "ok"
    return {
        "status": status,
        "discovered": discovered if discovered is not None else attempted,
        "attempted": attempted,
        "fetched": fetched,
        "errors": errors,
    }


def normalize_url(url: str) -> str:
    parsed = urlparse(url)
    scheme = parsed.scheme.lower() or "https"
    netloc = parsed.netloc.lower()
    path = parsed.path or "/"
    # Drop fragment; keep query
    return urlunparse((scheme, netloc, path, "", parsed.query, ""))


def same_host(url: str, base_host: str) -> bool:
    host = urlparse(url).netloc.lower()
    return host == base_host.lower() or host.removeprefix("www.") == base_host.removeprefix("www.")


def extract_links(html: str, base_url: str) -> list[str]:
    tree = HTMLParser(html)
    links: list[str] = []
    for node in tree.css("a[href]"):
        href = node.attributes.get("href")
        if not href or href.startswith(("#", "mailto:", "javascript:", "tel:")):
            continue
        abs_url = normalize_url(urljoin(base_url, href))
        links.append(abs_url)
    return links


def extract_title_meta(html: str) -> tuple[str | None, str | None, str | None]:
    tree = HTMLParser(html)
    title = None
    t = tree.css_first("title")
    if t and t.text():
        title = t.text().strip()
    robots_meta = None
    for meta in tree.css("meta[name]"):
        name = (meta.attributes.get("name") or "").lower()
        if name == "robots":
            robots_meta = meta.attributes.get("content")
            break
    canonical = None
    link = tree.css_first('link[rel="canonical"]')
    if link:
        canonical = link.attributes.get("href")
    return title, robots_meta, canonical


def crawl_demo(session: Session, job_id: str) -> CrawlOutcome:
    """Load fixture pages for https://demo.example/."""
    robots_text = load_demo_robots()
    rules = parse_robots(robots_text, USER_AGENT)
    from aeo_mvp.crawler.robots import robots_pass_value

    allowed = robots_pass_value(rules, "/")
    pages: list[Page] = []
    now = utc_now_iso()
    for fixture in load_demo_pages():
        title, robots_meta, canonical = extract_title_meta(fixture.html)
        page = Page(
            id=new_id(),
            job_id=job_id,
            url=fixture.url,
            final_url=fixture.url,
            source_url=fixture.url,
            content_representation="html",
            depth=fixture.depth,
            status_code=200,
            primary_status_code=200,
            primary_fetch_status="success",
            alternate_fetch_status="not_applicable",
            content_type="text/html; charset=utf-8",
            fetched_at=now,
            html=fixture.html,
            title=title or fixture.title,
            robots_meta=robots_meta,
            canonical_url=canonical,
            fetch_error=None,
        )
        session.add(page)
        pages.append(page)
    session.flush()
    logger.info("demo crawl loaded %s pages for job %s", len(pages), job_id)
    summary = _summarize_crawl_pages(pages, discovered=len(pages))
    return CrawlOutcome(
        pages=pages,
        robots_raw=robots_text,
        robots_allowed_root=allowed,
        crawl_status=str(summary["status"]),
        discovered=int(summary["discovered"]),
        attempted=int(summary["attempted"]),
        fetched=int(summary["fetched"]),
        errors=int(summary["errors"]),
    )


async def crawl_live(
    session: Session,
    job_id: str,
    base_url: str,
    *,
    max_pages: int = 25,
    max_depth: int = 2,
    timeout_s: float = 5.0,
) -> CrawlOutcome:
    settings = get_settings()
    max_pages = min(max_pages, settings.crawl_max_pages, 25)
    max_depth = min(max_depth, settings.crawl_max_depth, 2)
    try:
        base_url = assert_safe_public_url(base_url)
    except SSRFError as exc:
        raise RuntimeError(f"Unsafe crawl base URL rejected (SSRF): {exc}") from exc
    base_url = normalize_url(base_url)
    if not base_url.endswith("/") and urlparse(base_url).path in ("", "/"):
        base_url = base_url.rstrip("/") + "/"
    base_host = urlparse(base_url).netloc

    robots_raw: str | None = None
    robots_allowed = 0.5
    headers = default_headers()

    async with httpx.AsyncClient(headers=headers) as client:
        robots_url = urljoin(base_url, "/robots.txt")
        robots_result = await fetch_url(client, robots_url, timeout_s=timeout_s)
        rules = None
        if robots_result.status_code and robots_result.status_code < 400 and robots_result.text:
            robots_raw = robots_result.text
            rules = parse_robots(robots_raw, USER_AGENT)
            from aeo_mvp.crawler.robots import robots_pass_value

            robots_allowed = robots_pass_value(rules, "/")
        else:
            robots_allowed = 0.5

        queue: deque[tuple[str, int]] = deque([(base_url, 0)])
        seen: set[str] = set()
        pages: list[Page] = []

        while queue and len(pages) < max_pages:
            url, depth = queue.popleft()
            norm = normalize_url(url)
            if norm in seen:
                continue
            if not same_host(norm, base_host):
                continue
            if rules is not None:
                allowed = rules.is_allowed(path_from_url(norm))
                if allowed is False:
                    page = Page(
                        id=new_id(),
                        job_id=job_id,
                        url=norm,
                        final_url=norm,
                        source_url=None,
                        content_representation=None,
                        depth=depth,
                        status_code=None,
                        primary_status_code=None,
                        primary_fetch_status="failed",
                        alternate_fetch_status="not_attempted",
                        content_type=None,
                        fetched_at=utc_now_iso(),
                        html=None,
                        title=None,
                        robots_meta=None,
                        canonical_url=None,
                        fetch_error="blocked_by_robots",
                    )
                    session.add(page)
                    pages.append(page)
                    seen.add(norm)
                    continue

            seen.add(norm)
            outcome = await fetch_page_with_alternate(client, norm, timeout_s=timeout_s)
            # Logical/canonical article URL (strips one .md for direct Markdown URLs).
            logical_url = outcome.canonical_url or norm
            if logical_url != norm:
                seen.add(logical_url)
            title = robots_meta = canonical = None
            if outcome.html and outcome.representation == "html":
                title, robots_meta, canonical = extract_title_meta(outcome.html)
            if not title and outcome.title:
                title = outcome.title
            # For Markdown pages, persist logical article URL as same-host canonical.
            if outcome.representation == "markdown" and not canonical:
                canonical = logical_url
            page = Page(
                id=new_id(),
                job_id=job_id,
                url=logical_url,
                final_url=outcome.source_url or logical_url,
                source_url=outcome.source_url,
                content_representation=outcome.representation if outcome.html else None,
                depth=depth,
                status_code=outcome.status_code,
                primary_status_code=outcome.primary_status_code,
                primary_fetch_status=outcome.primary_fetch_status,
                alternate_fetch_status=outcome.alternate_fetch_status,
                content_type=outcome.content_type,
                fetched_at=datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
                html=outcome.html,
                source_markdown=outcome.source_markdown,
                title=title,
                robots_meta=robots_meta,
                canonical_url=canonical,
                fetch_error=outcome.fetch_error,
            )
            session.add(page)
            pages.append(page)

            # Link discovery is HTML-only. Markdown alternates are content-only
            # (do not invent a Markdown crawl frontier).
            if (
                outcome.html_discovery_ok
                and outcome.html
                and outcome.status_code
                and 200 <= outcome.status_code < 300
                and depth < max_depth
            ):
                for link in extract_links(outcome.html, outcome.source_url or norm):
                    if link not in seen and same_host(link, base_host):
                        queue.append((link, depth + 1))

        session.flush()
        logger.info("live crawl fetched %s pages for job %s", len(pages), job_id)
        summary = _summarize_crawl_pages(pages, discovered=len(seen))
        return CrawlOutcome(
            pages=pages,
            robots_raw=robots_raw,
            robots_allowed_root=robots_allowed,
            crawl_status=str(summary["status"]),
            discovered=int(summary["discovered"]),
            attempted=int(summary["attempted"]),
            fetched=int(summary["fetched"]),
            errors=int(summary["errors"]),
        )


async def crawl_site(
    session: Session,
    job_id: str,
    base_url: str,
    *,
    demo_mode: bool,
    max_pages: int = 25,
    max_depth: int = 2,
    timeout_s: float = 5.0,
) -> CrawlOutcome:
    if demo_mode:
        return crawl_demo(session, job_id)
    return await crawl_live(
        session,
        job_id,
        base_url,
        max_pages=max_pages,
        max_depth=max_depth,
        timeout_s=timeout_s,
    )
