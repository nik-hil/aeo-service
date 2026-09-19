"""SSRF URL allow-policy: public http(s) only, DNS revalidation per hop, IP pinning."""

from __future__ import annotations

import ipaddress
import socket
from dataclasses import dataclass
from urllib.parse import urlparse, urlunparse

import httpx


class SSRFError(ValueError):
    """Raised when a URL is blocked by the SSRF allow-policy."""


_BLOCKED_HOST_LABELS = frozenset({"localhost", "metadata", "metadata.google.internal"})


@dataclass(frozen=True)
class ValidatedFetchTarget:
    """
    Result of a single resolve+validate pass for one outbound hop.

    ``validated_ips`` are the only addresses that may be used for the TCP
    connect for this hop. The logical ``hostname`` remains for Host / SNI.
    """

    url: str
    scheme: str
    hostname: str
    port: int
    validated_ips: tuple[str, ...]

    @property
    def host_header(self) -> str:
        """Host header value (hostname + non-default port)."""
        default = 443 if self.scheme == "https" else 80
        if self.port == default:
            return self.hostname
        # IPv6 literals in Host need brackets when a port is present
        try:
            ipaddress.IPv6Address(self.hostname)
            return f"[{self.hostname}]:{self.port}"
        except ipaddress.AddressValueError:
            return f"{self.hostname}:{self.port}"


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


def normalize_public_url(url: str) -> str:
    """Normalize a URL for persistence: strip userinfo, lowercase host, keep path/query.

    Cheap parse-only helper (no DNS). Use for ``jobs.base_url`` so credentials never
    land in the DB. Authoritative SSRF remains at fetch via ``validate_url_for_fetch``.
    """
    return _normalize_url(url)


def _parse_special_ip_host(
    hostname: str,
) -> ipaddress.IPv4Address | ipaddress.IPv6Address | None:
    """Decode dotted/literal IPs plus decimal/hex integer IPv4 forms.

    Returns None when ``hostname`` is not an IP-shaped literal (DNS names stay None).
    Used by the create-time gate; fetch-time SSRF still resolves and validates.
    """
    host = (hostname or "").strip().lower().rstrip(".")
    if not host:
        return None
    try:
        return ipaddress.ip_address(host)
    except ValueError:
        pass
    # Decimal IPv4: http://2130706433/ → 127.0.0.1
    if host.isdigit():
        try:
            value = int(host)
            if 0 <= value <= 0xFFFFFFFF:
                return ipaddress.IPv4Address(value)
        except (ValueError, ipaddress.AddressValueError):
            return None
        return None
    # Hex IPv4: http://0x7f000001/ → 127.0.0.1
    if host.startswith("0x"):
        try:
            value = int(host, 16)
            if 0 <= value <= 0xFFFFFFFF:
                return ipaddress.IPv4Address(value)
        except (ValueError, ipaddress.AddressValueError):
            return None
    return None


def _hostname_from_netloc(netloc: str) -> str:
    # IPv6 in brackets: [::1]:8080
    if netloc.startswith("["):
        end = netloc.find("]")
        if end == -1:
            raise SSRFError(f"Invalid IPv6 host in URL netloc: {netloc!r}")
        return netloc[1:end]
    return netloc.rsplit(":", 1)[0]


def _port_from_netloc(netloc: str, scheme: str) -> int:
    if netloc.startswith("["):
        end = netloc.find("]")
        if end == -1:
            raise SSRFError(f"Invalid IPv6 host in URL netloc: {netloc!r}")
        rest = netloc[end + 1 :]
        if rest.startswith(":"):
            try:
                return int(rest[1:])
            except ValueError as exc:
                raise SSRFError(f"Invalid port in URL netloc: {netloc!r}") from exc
        return 443 if scheme == "https" else 80
    if ":" in netloc:
        host, _, port_s = netloc.rpartition(":")
        if host and port_s.isdigit():
            return int(port_s)
    return 443 if scheme == "https" else 80


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
    # Literal IP (dotted / bracketed) or decimal/hex integer forms?
    special = _parse_special_ip_host(hostname)
    if special is not None:
        if not _ip_is_public(special):
            raise SSRFError(f"Blocked non-public IP literal: {hostname}")
        return [str(special)]

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
    """Cheap pre-check (no DNS) for job-create: scheme, localhost, private literals.

    Also rejects decimal/hex integer IPv4 hosts (e.g. ``2130706433``, ``0x7f000001``).
    Does not replace fetch-time SSRF (DNS + IP pin); this is a create-time gate only.
    """
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
    special = _parse_special_ip_host(host)
    if special is not None:
        return not _ip_is_public(special)
    return False


def validate_url_for_fetch(url: str) -> ValidatedFetchTarget:
    """
    Parse/normalize URL, resolve DNS once, validate every address.

    Returns a target whose ``validated_ips`` must be used for the TCP connect
    for this hop (IP pinning). Do not resolve the hostname again at connect.
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
    port = _port_from_netloc(parsed.netloc, parsed.scheme)
    ips = tuple(_resolve_public_ips(host))
    return ValidatedFetchTarget(
        url=normalized,
        scheme=parsed.scheme,
        hostname=host,
        port=port,
        validated_ips=ips,
    )


def assert_safe_public_url(url: str) -> str:
    """
    Validate and normalize a URL for outbound fetch.

    Returns the normalized URL, or raises SSRFError.
    Resolves DNS and requires every A/AAAA to be a public address.
    """
    return validate_url_for_fetch(url).url


def pinned_connect_url(target: ValidatedFetchTarget, ip: str) -> str:
    """
    Rewrite ``target.url`` so the authority is ``ip`` (connection pin).

    Path/query are preserved. Caller must send Host / SNI for ``target.hostname``.
    """
    if ip not in target.validated_ips:
        raise SSRFError(f"Refusing to pin connect to non-validated IP: {ip}")
    # httpx.URL handles IPv6 brackets when host is set via copy_with
    logical = httpx.URL(target.url)
    return str(logical.copy_with(host=ip, port=target.port))


def request_extensions_for_pin(target: ValidatedFetchTarget) -> dict[str, str]:
    """httpcore extensions so TLS SNI / cert verify use the logical hostname."""
    if target.scheme == "https":
        return {"sni_hostname": target.hostname}
    return {}


__all__ = [
    "SSRFError",
    "ValidatedFetchTarget",
    "assert_safe_public_url",
    "is_obviously_unsafe_url",
    "normalize_public_url",
    "pinned_connect_url",
    "request_extensions_for_pin",
    "validate_url_for_fetch",
]
