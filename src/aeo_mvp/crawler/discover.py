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
            depth=fixture.depth,
            status_code=200,
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
    return CrawlOutcome(pages=pages, robots_raw=robots_text, robots_allowed_root=allowed)


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
                        depth=depth,
                        status_code=None,
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
            result = await fetch_url(client, norm, timeout_s=timeout_s)
            title = robots_meta = canonical = None
            if result.text:
                title, robots_meta, canonical = extract_title_meta(result.text)
            page = Page(
                id=new_id(),
                job_id=job_id,
                url=norm,
                final_url=result.final_url,
                depth=depth,
                status_code=result.status_code,
                content_type=result.content_type,
                fetched_at=datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
                html=result.text,
                title=title,
                robots_meta=robots_meta,
                canonical_url=canonical,
                fetch_error=result.error,
            )
            session.add(page)
            pages.append(page)

            if (
                result.text
                and result.status_code
                and 200 <= result.status_code < 300
                and depth < max_depth
            ):
                for link in extract_links(result.text, result.final_url or norm):
                    if link not in seen and same_host(link, base_host):
                        queue.append((link, depth + 1))

        session.flush()
        logger.info("live crawl fetched %s pages for job %s", len(pages), job_id)
        return CrawlOutcome(pages=pages, robots_raw=robots_raw, robots_allowed_root=robots_allowed)


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
