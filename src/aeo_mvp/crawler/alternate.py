"""Public alternate content representations (not a bot-challenge bypass).

When a primary HTML fetch is explicitly blocked (e.g. HTTP 403 / Cloudflare
challenge interstitial), some hosts expose a supported alternate URL that
returns the same article as plain Markdown. Hashnode article pages are the
first adapter: ``/slug`` → ``/slug.md``.

This module only proposes URLs. Fetches must still go through the normal
SSRF / IP-pin path in ``fetch_url``. Alternates are for **content** only —
crawl discovery continues to use HTML link extraction, never Markdown links.
"""

from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlparse, urlunparse

# Path prefixes that are not Hashnode *article* pages (no public .md twin).
_HASHNODE_NON_ARTICLE_PREFIXES = (
    "/series/",
    "/tag/",
    "/tags/",
    "/api/",
    "/cdn-cgi/",
    "/preview/",
    "/draft/",
    "/newsletter/",
    "/members/",
    "/badge/",
    "/widget/",
    "/embed/",
)

_CF_CHALLENGE_MARKERS = (
    "just a moment...",
    "cf-browser-verification",
    "cdn-cgi/challenge-platform",
    "attention required! | cloudflare",
    "enable javascript and cookies to continue",
    "checking your browser before accessing",
)


@dataclass(frozen=True)
class AlternateRepresentation:
    """A supported alternate content URL for a blocked primary page."""

    url: str
    representation: str  # e.g. "markdown"
    adapter: str  # e.g. "hashnode"


def looks_like_cloudflare_challenge(text: str | None, *, title: str | None = None) -> bool:
    """True when body/title resemble a Cloudflare interstitial (not article HTML)."""
    blob = f"{title or ''}\n{text or ''}".lower()
    if not blob.strip():
        return False
    return any(marker in blob for marker in _CF_CHALLENGE_MARKERS)


def is_primary_blocked(
    *,
    status_code: int | None,
    text: str | None = None,
    title: str | None = None,
) -> bool:
    """Explicit blocked/unavailable signal for alternate attempts.

    Initially: HTTP 403 and/or known Cloudflare challenge body/title.
    """
    if status_code == 403:
        return True
    return looks_like_cloudflare_challenge(text, title=title)


def is_primary_usable(
    *,
    status_code: int | None,
    text: str | None,
    error: str | None = None,
    title: str | None = None,
) -> bool:
    """Primary response can be analyzed as normal HTML (no alternate needed)."""
    if error:
        return False
    if status_code is None or not (200 <= status_code < 300):
        return False
    if not (text and str(text).strip()):
        return False
    if looks_like_cloudflare_challenge(text, title=title):
        return False
    return True


def _is_hashnode_publication_host(hostname: str) -> bool:
    host = (hostname or "").lower().strip(".").removeprefix("www.")
    # Tenant blogs: nik-hil.hashnode.dev — not the bare platform apex.
    return host.endswith(".hashnode.dev") and host != "hashnode.dev"


def _hashnode_article_alternate(url: str) -> AlternateRepresentation | None:
    parsed = urlparse((url or "").strip())
    if parsed.scheme not in ("http", "https"):
        return None
    if not _is_hashnode_publication_host(parsed.netloc):
        return None
    path = parsed.path or "/"
    path_lower = path.lower()
    if path_lower.endswith(".md"):
        return None
    if path in ("", "/"):
        return None
    for prefix in _HASHNODE_NON_ARTICLE_PREFIXES:
        if path_lower.startswith(prefix):
            return None
    # Single-segment-ish article slug; reject nested platform paths we don't know.
    # Allow multi-segment slugs (rare) but not empty trailing slash-only.
    slug_path = path.rstrip("/")
    if not slug_path or slug_path == "/":
        return None
    md_url = urlunparse(
        (parsed.scheme, parsed.netloc, f"{slug_path}.md", "", "", "")
    )
    return AlternateRepresentation(
        url=md_url,
        representation="markdown",
        adapter="hashnode",
    )


def get_supported_alternate_url(url: str) -> AlternateRepresentation | None:
    """Return a supported alternate content URL, or None.

    Hashnode articles are the first adapter. Non-Hashnode hosts, series pages,
    already-``.md`` URLs, and non-article paths return None (no request invented).
    """
    return _hashnode_article_alternate(url)
