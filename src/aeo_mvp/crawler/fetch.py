"""HTTP fetch helpers with timeout, UA, and SSRF-safe redirects."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from urllib.parse import urljoin

import httpx

from aeo_mvp.config import USER_AGENT
from aeo_mvp.security.ssrf import SSRFError, assert_safe_public_url

logger = logging.getLogger(__name__)

MAX_REDIRECTS = 5


@dataclass
class FetchResult:
    url: str
    final_url: str
    status_code: int | None
    content_type: str | None
    text: str | None
    error: str | None = None


async def fetch_url(
    client: httpx.AsyncClient,
    url: str,
    *,
    timeout_s: float = 5.0,
    max_redirects: int = MAX_REDIRECTS,
) -> FetchResult:
    """
    Fetch a URL with SSRF validation on the initial URL and every redirect hop.

    Does not auto-follow redirects; manually follows up to ``max_redirects``
    after re-validating each Location (absolute or joined).
    """
    current = url
    try:
        for hop in range(max_redirects + 1):
            safe = assert_safe_public_url(current)
            resp = await client.get(safe, timeout=timeout_s, follow_redirects=False)

            if resp.status_code in (301, 302, 303, 307, 308):
                location = resp.headers.get("location")
                if not location:
                    return FetchResult(
                        url=url,
                        final_url=safe,
                        status_code=resp.status_code,
                        content_type=resp.headers.get("content-type"),
                        text=None,
                        error="redirect_missing_location",
                    )
                next_url = urljoin(safe, location)
                try:
                    assert_safe_public_url(next_url)
                except SSRFError as exc:
                    logger.warning("SSRF blocked redirect %s → %s: %s", safe, next_url, exc)
                    return FetchResult(
                        url=url,
                        final_url=safe,
                        status_code=resp.status_code,
                        content_type=resp.headers.get("content-type"),
                        text=None,
                        error=f"ssrf_redirect_blocked: {exc}",
                    )
                if hop >= max_redirects:
                    return FetchResult(
                        url=url,
                        final_url=safe,
                        status_code=resp.status_code,
                        content_type=resp.headers.get("content-type"),
                        text=None,
                        error=f"too_many_redirects (>{max_redirects})",
                    )
                current = next_url
                continue

            content_type = resp.headers.get("content-type")
            text = (
                resp.text
                if "html" in (content_type or "").lower() or resp.status_code < 400
                else None
            )
            if text is None and resp.status_code < 400:
                text = resp.text
            return FetchResult(
                url=url,
                final_url=str(resp.url) if resp.url else safe,
                status_code=resp.status_code,
                content_type=content_type,
                text=text,
                error=None,
            )

        return FetchResult(
            url=url,
            final_url=current,
            status_code=None,
            content_type=None,
            text=None,
            error=f"too_many_redirects (>{max_redirects})",
        )
    except SSRFError as exc:
        logger.warning("SSRF blocked fetch for %s: %s", url, exc)
        return FetchResult(
            url=url,
            final_url=url,
            status_code=None,
            content_type=None,
            text=None,
            error=f"ssrf_blocked: {exc}",
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("fetch failed for %s: %s", url, exc)
        return FetchResult(
            url=url,
            final_url=url,
            status_code=None,
            content_type=None,
            text=None,
            error=str(exc),
        )


def default_headers() -> dict[str, str]:
    return {"User-Agent": USER_AGENT, "Accept": "text/html,application/xhtml+xml"}
