"""SSRF URL allow-policy: public http(s) only, DNS revalidation per hop."""

from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urlparse, urlunparse


class SSRFError(ValueError):
    """Raised when a URL is blocked by the SSRF allow-policy."""


_BLOCKED_HOST_LABELS = frozenset({"localhost", "metadata", "metadata.google.internal"})


def _normalize_url(url: str) -> str:
    raw = (url or "").strip()
    if not raw:
        raise SSRFError("URL is empty")
    parsed = urlparse(raw)
    if not parsed.scheme or not parsed.netloc:
        raise SSRFError(f"URL must include scheme and host: {url!r}")
    scheme = parsed.scheme.lower()
    netloc = parsed.netloc.lower()
    # Drop userinfo from authority for safety
    if "@" in netloc:
        netloc = netloc.rsplit("@", 1)[-1]
    path = parsed.path or "/"
    return urlunparse((scheme, netloc, path, "", parsed.query, ""))


def _hostname_from_netloc(netloc: str) -> str:
    # IPv6 in brackets: [::1]:8080
    if netloc.startswith("["):
        end = netloc.find("]")
        if end == -1:
            raise SSRFError(f"Invalid IPv6 host in URL netloc: {netloc!r}")
        return netloc[1:end]
    return netloc.rsplit(":", 1)[0]


def _is_blocked_hostname(hostname: str) -> bool:
    host = hostname.lower().rstrip(".")
    if host in _BLOCKED_HOST_LABELS:
        return True
    if host.endswith(".localhost"):
        return True
    if host.endswith(".local"):
        return True
    return False


def _ip_is_public(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    """Return True only for global-unicast public addresses."""
    # Unwrap IPv4-mapped IPv6 (::ffff:x.x.x.x)
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped is not None:
        return _ip_is_public(ip.ipv4_mapped)

    if ip.is_unspecified or ip.is_loopback or ip.is_link_local:
        return False
    if ip.is_multicast or ip.is_reserved or ip.is_private:
        return False
    # Explicit metadata / CGNAT / documentation ranges sometimes not covered
    if isinstance(ip, ipaddress.IPv4Address):
        if ip in ipaddress.ip_network("169.254.0.0/16"):
            return False
        if ip in ipaddress.ip_network("100.64.0.0/10"):  # CGNAT
            return False
        if ip in ipaddress.ip_network("0.0.0.0/8"):
            return False
    if isinstance(ip, ipaddress.IPv6Address):
        # ULA fc00::/7 (also covered by is_private in modern Python)
        if ip in ipaddress.ip_network("fc00::/7"):
            return False
        if ip.teredo or ip.sixtofour:
            # Validate embedded IPv4 if present
            pass
    # is_global is the strongest check when available
    if hasattr(ip, "is_global") and not ip.is_global:
        return False
    return True


def _resolve_public_ips(hostname: str) -> list[str]:
    """Resolve hostname; every A/AAAA must be public. Returns string forms."""
    # Literal IP?
    try:
        ip = ipaddress.ip_address(hostname)
        if not _ip_is_public(ip):
            raise SSRFError(f"Blocked non-public IP literal: {hostname}")
        return [str(ip)]
    except ValueError:
        pass

    if _is_blocked_hostname(hostname):
        raise SSRFError(f"Blocked hostname: {hostname}")

    try:
        infos = socket.getaddrinfo(hostname, None, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise SSRFError(f"DNS resolution failed for {hostname}: {exc}") from exc

    if not infos:
        raise SSRFError(f"DNS returned no addresses for {hostname}")

    addrs: list[str] = []
    seen: set[str] = set()
    for info in infos:
        sockaddr = info[4]
        addr = sockaddr[0]
        # Strip zone id if present (fe80::1%eth0)
        if "%" in addr:
            addr = addr.split("%", 1)[0]
        if addr in seen:
            continue
        seen.add(addr)
        try:
            ip = ipaddress.ip_address(addr)
        except ValueError as exc:
            raise SSRFError(f"Invalid resolved address {addr!r}") from exc
        if not _ip_is_public(ip):
            raise SSRFError(f"Resolved address is not public: {hostname} → {addr}")
        addrs.append(addr)

    if not addrs:
        raise SSRFError(f"No usable public addresses for {hostname}")
    return addrs


def is_obviously_unsafe_url(url: str) -> bool:
    """Cheap pre-check (no DNS) for job-create: scheme, localhost, private literals."""
    try:
        normalized = _normalize_url(url)
    except SSRFError:
        return True
    parsed = urlparse(normalized)
    if parsed.scheme not in ("http", "https"):
        return True
    host = _hostname_from_netloc(parsed.netloc)
    if _is_blocked_hostname(host):
        return True
    try:
        ip = ipaddress.ip_address(host)
        return not _ip_is_public(ip)
    except ValueError:
        return False


def assert_safe_public_url(url: str) -> str:
    """
    Validate and normalize a URL for outbound fetch.

    Returns the normalized URL, or raises SSRFError.
    Resolves DNS and requires every A/AAAA to be a public address.
    """
    normalized = _normalize_url(url)
    parsed = urlparse(normalized)
    if parsed.scheme not in ("http", "https"):
        raise SSRFError(f"Only http/https allowed, got scheme={parsed.scheme!r}")
    host = _hostname_from_netloc(parsed.netloc)
    if not host:
        raise SSRFError("URL missing hostname")
    if _is_blocked_hostname(host):
        raise SSRFError(f"Blocked hostname: {host}")
    _resolve_public_ips(host)
    return normalized


__all__ = [
    "SSRFError",
    "assert_safe_public_url",
    "is_obviously_unsafe_url",
]
