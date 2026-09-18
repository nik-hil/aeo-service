"""Public Suffix List–based registrable domain parsing."""

from __future__ import annotations

from urllib.parse import urlparse

import tldextract

# Prefer bundled/public suffix data; avoid surprise network fetches in tests/CI.
_EXTRACTOR = tldextract.TLDExtract(suffix_list_urls=())


def registrable_domain(url_or_host: str) -> str:
    """Return the registrable domain (eTLD+1) for a URL or hostname.

    Examples:
      example.com → example.com
      www.example.com / blog.example.com → example.com
      example.co.uk → example.co.uk
      malicious-example.com ≠ example.com
    """
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
        # IPv6 literal — return without brackets/port handling complexity
        end = host.find("]")
        host = host[1:end]
    elif ":" in host:
        host = host.rsplit(":", 1)[0]
    host = host.strip(".")
    if not host:
        return ""

    ext = _EXTRACTOR(host)
    if ext.domain and ext.suffix:
        return f"{ext.domain}.{ext.suffix}".lower()
    # IPs, unrecognized TLDs (e.g. demo.example), or bare labels:
    # keep the full hostname minus a single leading www.
    return host.removeprefix("www.")
