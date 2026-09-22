"""Fetch a page with optional public alternate content representation.

Flow:
1. Fetch the user/canonical URL via the normal SSRF + IP-pin path.
2. If primary is usable 2xx HTML → keep it; do not request an alternate.
3. Only when primary is explicitly blocked/unavailable **and** a supported
   alternate exists → fetch the alternate through the **same** fetch path.
4. Markdown alternates are normalized to analyzable HTML; HTML discovery is
   never driven from Markdown links.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import httpx

from aeo_mvp.crawler.alternate import (
    AlternateRepresentation,
    get_supported_alternate_url,
    is_primary_blocked,
    is_primary_usable,
)
from aeo_mvp.crawler.fetch import FetchResult, fetch_url
from aeo_mvp.crawler.markdown_normalize import markdown_to_analyzable_html

logger = logging.getLogger(__name__)

PrimaryFetchStatus = str  # success | blocked | failed
AlternateFetchStatus = str  # not_applicable | not_attempted | success | failed


@dataclass
class PageFetchOutcome:
    """Provenance-aware page fetch for the crawl pipeline."""

    canonical_url: str
    source_url: str
    representation: str  # html | markdown
    status_code: int | None
    content_type: str | None
    # Analyzable HTML body (normalized from Markdown when representation=markdown).
    html: str | None
    title: str | None
    fetch_error: str | None
    primary_status_code: int | None
    primary_fetch_status: PrimaryFetchStatus
    alternate_fetch_status: AlternateFetchStatus
    primary_error: str | None = None
    alternate_error: str | None = None
    alternate: AlternateRepresentation | None = None
    # True only when analyzable body came from real HTML (safe for link discovery).
    html_discovery_ok: bool = False


def _primary_status(result: FetchResult) -> PrimaryFetchStatus:
    if is_primary_usable(
        status_code=result.status_code, text=result.text, error=result.error
    ):
        return "success"
    if is_primary_blocked(status_code=result.status_code, text=result.text):
        return "blocked"
    return "failed"


def _diagnose_unavailable(
    *,
    primary: FetchResult,
    alternate: FetchResult | None,
    alt_meta: AlternateRepresentation | None,
) -> str:
    parts = [
        f"primary_unavailable: status={primary.status_code!r} "
        f"error={primary.error!r}"
    ]
    if alt_meta is None:
        parts.append("alternate=not_applicable")
    elif alternate is None:
        parts.append("alternate=not_attempted")
    else:
        parts.append(
            f"alternate_failed: url={alt_meta.url!r} status={alternate.status_code!r} "
            f"error={alternate.error!r}"
        )
    return "; ".join(parts)


async def fetch_page_with_alternate(
    client: httpx.AsyncClient,
    url: str,
    *,
    timeout_s: float = 5.0,
) -> PageFetchOutcome:
    """Fetch ``url``, optionally falling back to a supported public alternate."""
    primary = await fetch_url(client, url, timeout_s=timeout_s)
    alt_meta = get_supported_alternate_url(url)
    primary_status = _primary_status(primary)

    if primary_status == "success":
        return PageFetchOutcome(
            canonical_url=url,
            source_url=primary.final_url or url,
            representation="html",
            status_code=primary.status_code,
            content_type=primary.content_type,
            html=primary.text,
            title=None,
            fetch_error=None,
            primary_status_code=primary.status_code,
            primary_fetch_status="success",
            alternate_fetch_status=(
                "not_attempted" if alt_meta is not None else "not_applicable"
            ),
            primary_error=None,
            alternate=alt_meta,
            html_discovery_ok=True,
        )

    # Only attempt alternate on explicit blocked/unavailable + supported twin.
    if primary_status != "blocked" or alt_meta is None:
        err = primary.error
        if primary_status == "blocked" and alt_meta is None:
            err = _diagnose_unavailable(
                primary=primary, alternate=None, alt_meta=None
            )
        elif primary_status == "failed" and not err:
            err = (
                f"primary_unavailable: status={primary.status_code!r} "
                f"error={primary.error!r}"
            )
        return PageFetchOutcome(
            canonical_url=url,
            source_url=primary.final_url or url,
            representation="html",
            status_code=primary.status_code,
            content_type=primary.content_type,
            html=None,
            title=None,
            fetch_error=err,
            primary_status_code=primary.status_code,
            primary_fetch_status=primary_status,
            alternate_fetch_status=(
                "not_applicable" if alt_meta is None else "not_attempted"
            ),
            primary_error=primary.error,
            alternate=alt_meta,
            html_discovery_ok=False,
        )

    logger.info(
        "Primary blocked for %s (status=%s); trying %s alternate %s",
        url,
        primary.status_code,
        alt_meta.adapter,
        alt_meta.url,
    )
    alternate = await fetch_url(client, alt_meta.url, timeout_s=timeout_s)
    alt_ok = (
        not alternate.error
        and alternate.status_code is not None
        and 200 <= alternate.status_code < 300
        and bool(alternate.text and alternate.text.strip())
    )
    if not alt_ok:
        return PageFetchOutcome(
            canonical_url=url,
            source_url=url,
            representation="html",
            status_code=primary.status_code,
            content_type=primary.content_type,
            html=None,
            title=None,
            fetch_error=_diagnose_unavailable(
                primary=primary, alternate=alternate, alt_meta=alt_meta
            ),
            primary_status_code=primary.status_code,
            primary_fetch_status="blocked",
            alternate_fetch_status="failed",
            primary_error=primary.error,
            alternate_error=alternate.error,
            alternate=alt_meta,
            html_discovery_ok=False,
        )

    if alt_meta.representation == "markdown":
        normalized = markdown_to_analyzable_html(alternate.text or "")
        return PageFetchOutcome(
            canonical_url=url,
            source_url=alternate.final_url or alt_meta.url,
            representation="markdown",
            status_code=alternate.status_code,
            content_type=alternate.content_type or "text/markdown",
            html=normalized.html,
            title=normalized.title,
            fetch_error=None,
            primary_status_code=primary.status_code,
            primary_fetch_status="blocked",
            alternate_fetch_status="success",
            primary_error=primary.error,
            alternate_error=None,
            alternate=alt_meta,
            # Markdown is content-only — do not drive HTML link discovery.
            html_discovery_ok=False,
        )

    # Future non-markdown adapters could land here.
    return PageFetchOutcome(
        canonical_url=url,
        source_url=alternate.final_url or alt_meta.url,
        representation=alt_meta.representation,
        status_code=alternate.status_code,
        content_type=alternate.content_type,
        html=alternate.text,
        title=None,
        fetch_error=None,
        primary_status_code=primary.status_code,
        primary_fetch_status="blocked",
        alternate_fetch_status="success",
        primary_error=primary.error,
        alternate=alt_meta,
        html_discovery_ok=False,
    )
