"""HTTP fetch helpers with timeout and UA."""

from __future__ import annotations

import logging
from dataclasses import dataclass

import httpx

from aeo_mvp.config import USER_AGENT

logger = logging.getLogger(__name__)


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
) -> FetchResult:
    try:
        resp = await client.get(url, timeout=timeout_s, follow_redirects=True)
        content_type = resp.headers.get("content-type")
        text = resp.text if "html" in (content_type or "").lower() or resp.status_code < 400 else None
        if text is None and resp.status_code < 400:
            text = resp.text
        return FetchResult(
            url=url,
            final_url=str(resp.url),
            status_code=resp.status_code,
            content_type=content_type,
            text=text,
            error=None,
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
