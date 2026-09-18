"""Public Suffix List–based registrable domain parsing.

``registrable_domain()`` is TRUE PSL eTLD+1 (with private domains enabled).
It is **not** the AI-search target match key — use ``aeo_mvp.target_site.target_match``.
"""

from __future__ import annotations

from urllib.parse import urlparse

import tldextract

# Prefer bundled/public suffix data; avoid surprise network fetches in tests/CI.
# Private domains ON so alice.github.io → alice.github.io (not github.io).
# Note: hashnode.dev is NOT on PSL PRIVATE; eTLD+1(nik-hil.hashnode.dev) remains
# hashnode.dev — that is correct PSL math. Publication isolation uses hostname
# scope + supplemental allowlist (see aeo_mvp.target_site / DOMAIN_MATCHING.md).
_EXTRACTOR = tldextract.TLDExtract(
    suffix_list_urls=(),
    include_psl_private_domains=True,
)

# Public-only extractor for detecting private-suffix multi-tenant platforms.
_EXTRACTOR_PUBLIC_ONLY = tldextract.TLDExtract(
    suffix_list_urls=(),
    include_psl_private_domains=False,
)


def _host_from_url_or_host(url_or_host: str) -> str:
    raw = (url_or_host or "").strip()
    if not raw:
        return ""
    if "://" in raw:
        host = urlparse(raw).netloc
    else:
        host = raw
    host = host.lower()
    if "@" in host:
        host = host.rsplit("@", 1)[-1]
    if host.startswith("[") and "]" in host:
        end = host.find("]")
        host = host[1:end]
    elif ":" in host:
        host = host.rsplit(":", 1)[0]
    return host.strip(".")


def _registrable_with(extractor: tldextract.TLDExtract, host: str) -> str:
    if not host:
        return ""
    ext = extractor(host)
    if ext.domain and ext.suffix:
        return f"{ext.domain}.{ext.suffix}".lower()
    # IPs, unrecognized TLDs (e.g. demo.example), or bare labels:
    # keep the full hostname minus a single leading www.
    return host.removeprefix("www.")


def registrable_domain(url_or_host: str) -> str:
    """Return the registrable domain (eTLD+1) for a URL or hostname.

    Uses the Public Suffix List with **private domains enabled**.

    Examples:
      example.com → example.com
      www.example.com / blog.example.com → example.com
      example.co.uk → example.co.uk
      alice.github.io → alice.github.io  (private suffix)
      nik-hil.hashnode.dev → hashnode.dev  (hashnode.dev is NOT PSL-private)
      malicious-example.com ≠ example.com
    """
    host = _host_from_url_or_host(url_or_host)
    if not host:
        return ""
    return _registrable_with(_EXTRACTOR, host)


def registrable_domain_public_only(url_or_host: str) -> str:
    """eTLD+1 ignoring PSL private domains (diagnostic / multi-tenant detection)."""
    host = _host_from_url_or_host(url_or_host)
    if not host:
        return ""
    return _registrable_with(_EXTRACTOR_PUBLIC_ONLY, host)
