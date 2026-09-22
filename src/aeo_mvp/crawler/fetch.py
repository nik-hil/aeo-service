"""HTTP fetch helpers with timeout, UA, SSRF-safe redirects, and IP pinning."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from urllib.parse import urljoin

import httpx

from aeo_mvp.config import USER_AGENT
from aeo_mvp.security.ssrf import (
    SSRFError,
    ValidatedFetchTarget,
    pinned_connect_url,
    request_extensions_for_pin,
    validate_url_for_fetch,
)

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


async def _get_pinned(
    client: httpx.AsyncClient,
    target: ValidatedFetchTarget,
    *,
    timeout_s: float,
) -> httpx.Response:
    """
    GET connecting only to a validated IP for this hop.

    Logical hostname is preserved via Host header and TLS ``sni_hostname``
    (certificate verification stays enabled). DNS is not re-resolved at connect.
    """
    headers = {"Host": target.host_header}
    extensions = request_extensions_for_pin(target)
    last_exc: Exception | None = None
    for ip in target.validated_ips:
        connect_url = pinned_connect_url(target, ip)
        try:
            return await client.get(
                connect_url,
                headers=headers,
                timeout=timeout_s,
                follow_redirects=False,
                extensions=extensions,
            )
        except (httpx.ConnectError, httpx.ConnectTimeout) as exc:
            last_exc = exc
            logger.debug(
                "Pinned connect to %s (%s) failed: %s",
                ip,
                target.hostname,
                exc,
            )
            continue
    if last_exc is not None:
        raise last_exc
    raise SSRFError(f"No validated IPs to connect for {target.hostname}")


async def fetch_url(
    client: httpx.AsyncClient,
    url: str,
    *,
    timeout_s: float = 5.0,
    max_redirects: int = MAX_REDIRECTS,
) -> FetchResult:
    """
    Fetch a URL with SSRF validation + IP pinning on the initial URL and every redirect hop.

    Does not auto-follow redirects; manually follows up to ``max_redirects``
    after re-validating each Location (absolute or joined). Each hop resolves
    DNS once, validates every address, and connects only to those IPs.
    """
    current = url
    # When set, the next hop must use this already-resolved target (no second DNS).
    pending_target: ValidatedFetchTarget | None = None
    try:
        for hop in range(max_redirects + 1):
            if pending_target is not None:
                target = pending_target
                pending_target = None
            else:
                target = validate_url_for_fetch(current)
            safe = target.url
            resp = await _get_pinned(client, target, timeout_s=timeout_s)

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
                    # Fresh resolve+validate for the redirect hop only — the
                    # same ValidatedFetchTarget is reused for the next connect
                    # (never resolve again between validate and connect).
                    pending_target = validate_url_for_fetch(next_url)
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
            # Prefer logical URL for final_url (not the IP-pinned connect URL)
            final = safe
            return FetchResult(
                url=url,
                final_url=final,
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
    # Include markdown so public .md alternates (e.g. Hashnode) are acceptable.
    return {
        "User-Agent": USER_AGENT,
        "Accept": "text/html,application/xhtml+xml,text/markdown,text/plain;q=0.9,*/*;q=0.8",
    }
