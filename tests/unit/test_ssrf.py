"""Unit tests for SSRF URL allow-policy and DNS-rebinding IP pinning."""

from __future__ import annotations

import ipaddress
import socket
import ssl
import subprocess
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock
from urllib.parse import urlparse

import httpcore
import httpx
import pytest

from aeo_mvp.crawler.fetch import fetch_url
from aeo_mvp.security.ssrf import (
    SSRFError,
    assert_safe_public_url,
    is_obviously_unsafe_url,
    pinned_connect_url,
    request_extensions_for_pin,
    validate_url_for_fetch,
)

PUBLIC_V4 = "93.184.216.34"
PUBLIC_V6 = "2606:2800:220:1:248:1893:25c8:1946"
METADATA_V4 = "169.254.169.254"
PRIVATE_V6 = "fd12:3456:789a:1::1"


def _gai(ip: str, port: int = 0):
    parsed = ipaddress.ip_address(ip)
    if isinstance(parsed, ipaddress.IPv6Address):
        return [(socket.AF_INET6, socket.SOCK_STREAM, 6, "", (ip, port, 0, 0))]
    return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (ip, port))]


@pytest.mark.parametrize(
    "url",
    [
        "http://localhost/",
        "https://localhost/path",
        "http://127.0.0.1/",
        "http://10.0.0.1/",
        "http://192.168.1.1/",
        "http://172.16.5.5/",
        "http://169.254.169.254/latest/meta-data/",
        "http://[::1]/",
        "file:///etc/passwd",
        "ftp://example.com/file",
        "http://100.64.0.1/",  # CGNAT
        "http://224.0.0.1/",  # multicast
        "http://[::ffff:127.0.0.1]/",  # IPv4-mapped loopback
        "http://[::ffff:10.1.2.3]/",  # IPv4-mapped RFC1918
        "http://[fe80::1]/",  # link-local IPv6
        "http://[ff02::1]/",  # multicast IPv6
        "http://0.0.0.0/",
        "http://metadata.google.internal/",
        "http://foo.localhost/",
        "http://printer.local/",
    ],
)
def test_blocked_urls(url: str) -> None:
    with pytest.raises(SSRFError):
        assert_safe_public_url(url)


def test_public_example_com_passes_validation() -> None:
    try:
        out = assert_safe_public_url("https://example.com/path")
    except SSRFError as exc:
        msg = str(exc).lower()
        if "dns" in msg or "resolution" in msg or "failed" in msg:
            pytest.skip(f"live DNS unavailable: {exc}")
        raise
    assert out.startswith("https://example.com")


def test_redirect_target_private_ip_rejected() -> None:
    with pytest.raises(SSRFError):
        assert_safe_public_url("http://127.0.0.1/redirect-target")


def test_is_obviously_unsafe_covers_literals() -> None:
    assert is_obviously_unsafe_url("http://127.0.0.1/") is True
    assert is_obviously_unsafe_url("http://10.0.0.1/") is True
    assert is_obviously_unsafe_url("https://example.com/") is False


@pytest.mark.asyncio
async def test_fetch_url_blocks_redirect_to_private(monkeypatch: pytest.MonkeyPatch) -> None:
    public_host = "example.com"

    def fake_getaddrinfo(host, *args, **kwargs):  # noqa: ANN001
        if host in {"127.0.0.1", "localhost"} or str(host).startswith("127."):
            return _gai("127.0.0.1")
        return _gai(PUBLIC_V4)

    monkeypatch.setattr("socket.getaddrinfo", fake_getaddrinfo)

    calls = {"n": 0}

    async def fake_get(url, **kwargs):  # noqa: ANN001
        calls["n"] += 1
        resp = MagicMock()
        if calls["n"] == 1:
            resp.status_code = 302
            resp.headers = {"location": "http://127.0.0.1/secret"}
            resp.url = url
            resp.text = ""
            return resp
        resp.status_code = 200
        resp.headers = {"content-type": "text/html"}
        resp.url = url
        resp.text = "<html></html>"
        return resp

    client = MagicMock()
    client.get = AsyncMock(side_effect=fake_get)

    result = await fetch_url(client, f"https://{public_host}/start")
    assert result.error is not None
    assert "ssrf" in result.error.lower()


# ---------------------------------------------------------------------------
# P0-2: DNS rebinding TOCTOU — IP pinning
# ---------------------------------------------------------------------------


class _RebindDNS:
    """Deterministic getaddrinfo: first resolve public, later resolves blocked."""

    def __init__(self, host: str, first_ip: str, later_ip: str) -> None:
        self.host = host
        self.first_ip = first_ip
        self.later_ip = later_ip
        self.calls: list[str] = []

    def __call__(self, host, *args, **kwargs):  # noqa: ANN001
        h = str(host)
        self.calls.append(h)
        try:
            ipaddress.ip_address(h)
            return _gai(h)
        except ValueError:
            pass
        if h == self.host or h.rstrip(".") == self.host:
            count = sum(1 for c in self.calls if c == h or c.rstrip(".") == self.host)
            if count <= 1:
                return _gai(self.first_ip)
            return _gai(self.later_ip)
        raise socket.gaierror(socket.EAI_NONAME, f"no mock DNS for {host}")


@pytest.mark.asyncio
async def test_direct_rebinding_pins_validated_ip_not_loopback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Validate sees PUBLIC_V4; a second resolve would be 127.0.0.1 — never connect there."""
    host = "rebind.example"
    dns = _RebindDNS(host, PUBLIC_V4, "127.0.0.1")
    monkeypatch.setattr("socket.getaddrinfo", dns)

    connected: list[tuple[str, int]] = []

    async def spy_connect(
        self, host, port, timeout=None, local_address=None, socket_options=None
    ):  # noqa: ANN001
        connected.append((str(host), int(port)))
        raise OSError("test: refuse real network")

    monkeypatch.setattr(httpcore.AnyIOBackend, "connect_tcp", spy_connect)

    async with httpx.AsyncClient() as client:
        result = await fetch_url(client, f"https://{host}/page", timeout_s=1.0)

    assert connected, "expected a connect attempt"
    assert all(ip != "127.0.0.1" for ip, _ in connected)
    assert connected[0][0] == PUBLIC_V4
    host_resolves = [c for c in dns.calls if c == host]
    assert len(host_resolves) == 1
    assert result.error is not None  # connect refused by spy


@pytest.mark.asyncio
async def test_metadata_rebinding_never_connects_to_metadata(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    host = "meta-rebind.example"
    dns = _RebindDNS(host, PUBLIC_V4, METADATA_V4)
    monkeypatch.setattr("socket.getaddrinfo", dns)

    connected: list[str] = []

    async def spy_connect(
        self, host, port, timeout=None, local_address=None, socket_options=None
    ):  # noqa: ANN001
        connected.append(str(host))
        raise OSError("test: refuse real network")

    monkeypatch.setattr(httpcore.AnyIOBackend, "connect_tcp", spy_connect)

    async with httpx.AsyncClient() as client:
        await fetch_url(client, f"http://{host}/latest/meta-data/", timeout_s=1.0)

    assert connected == [PUBLIC_V4]
    assert METADATA_V4 not in connected
    assert len([c for c in dns.calls if c == host]) == 1


@pytest.mark.asyncio
async def test_ipv6_rebinding_never_connects_to_private_v6(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    host = "v6-rebind.example"
    dns = _RebindDNS(host, PUBLIC_V6, PRIVATE_V6)
    monkeypatch.setattr("socket.getaddrinfo", dns)

    connected: list[str] = []

    async def spy_connect(
        self, host, port, timeout=None, local_address=None, socket_options=None
    ):  # noqa: ANN001
        connected.append(str(host))
        raise OSError("test: refuse real network")

    monkeypatch.setattr(httpcore.AnyIOBackend, "connect_tcp", spy_connect)

    async with httpx.AsyncClient() as client:
        await fetch_url(client, f"https://{host}/", timeout_s=1.0)

    assert connected == [PUBLIC_V6]
    assert PRIVATE_V6 not in connected


@pytest.mark.asyncio
async def test_redirect_rebinding_blocked_before_private_connect(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Redirect host public at validate then private before connect → no private connect."""
    start_host = "start.example"
    redir_host = "redir-rebind.example"
    resolve_counts: dict[str, int] = {}

    def fake_getaddrinfo(host, *args, **kwargs):  # noqa: ANN001
        h = str(host)
        try:
            ipaddress.ip_address(h)
            return _gai(h)
        except ValueError:
            pass
        resolve_counts[h] = resolve_counts.get(h, 0) + 1
        if h == start_host:
            return _gai(PUBLIC_V4)
        if h == redir_host:
            if resolve_counts[h] == 1:
                return _gai(PUBLIC_V4)
            return _gai("10.0.0.1")
        raise socket.gaierror(socket.EAI_NONAME, h)

    monkeypatch.setattr("socket.getaddrinfo", fake_getaddrinfo)

    get_calls: list[dict] = []
    hop = {"n": 0}

    async def fake_get(url, **kwargs):  # noqa: ANN001
        get_calls.append({"url": str(url), "headers": kwargs.get("headers"), "extensions": kwargs.get("extensions")})
        hop["n"] += 1
        resp = MagicMock()
        if hop["n"] == 1:
            resp.status_code = 302
            resp.headers = {"location": f"https://{redir_host}/next"}
            resp.url = url
            resp.text = ""
            return resp
        resp.status_code = 200
        resp.headers = {"content-type": "text/html"}
        resp.url = url
        resp.text = "<html>ok</html>"
        return resp

    client = MagicMock()
    client.get = AsyncMock(side_effect=fake_get)

    result = await fetch_url(client, f"https://{start_host}/start")
    assert result.error is None
    assert len(get_calls) == 2

    for call in get_calls:
        parsed = urlparse(call["url"])
        assert parsed.hostname == PUBLIC_V4
        assert "10.0.0.1" not in call["url"]

    assert get_calls[1]["headers"]["Host"] == redir_host
    assert get_calls[1]["extensions"]["sni_hostname"] == redir_host
    assert resolve_counts.get(redir_host) == 1


def _make_self_signed_cert(tmp_path: Path, hostname: str) -> tuple[Path, Path]:
    cert_path = tmp_path / "cert.pem"
    key_path = tmp_path / "key.pem"
    subprocess.run(
        [
            "openssl",
            "req",
            "-x509",
            "-newkey",
            "rsa:2048",
            "-keyout",
            str(key_path),
            "-out",
            str(cert_path),
            "-days",
            "1",
            "-nodes",
            "-subj",
            f"/CN={hostname}",
            "-addext",
            f"subjectAltName=DNS:{hostname}",
        ],
        check=True,
        capture_output=True,
    )
    return cert_path, key_path


@pytest.mark.asyncio
async def test_pinned_https_tls_verify_sni_host_local(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Local HTTPS server: IP pin preserves TLS verify + SNI + Host (no live external DNS)."""
    hostname = "pin-tls.test"
    import aeo_mvp.security.ssrf as ssrf_mod

    real_public = ssrf_mod._ip_is_public

    def allow_loopback_for_fixture(ip):  # noqa: ANN001
        if ip.is_loopback:
            return True
        return real_public(ip)

    monkeypatch.setattr(ssrf_mod, "_ip_is_public", allow_loopback_for_fixture)

    def fake_getaddrinfo(host, *args, **kwargs):  # noqa: ANN001
        h = str(host)
        if h in {hostname, "127.0.0.1"}:
            return _gai("127.0.0.1")
        try:
            ipaddress.ip_address(h)
            return _gai(h)
        except ValueError as exc:
            raise socket.gaierror(socket.EAI_NONAME, h) from exc

    monkeypatch.setattr("socket.getaddrinfo", fake_getaddrinfo)

    cert_path, key_path = _make_self_signed_cert(tmp_path, hostname)
    seen_host_header: list[str] = []

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802
            seen_host_header.append(self.headers.get("Host", ""))
            body = b"<html>pinned-ok</html>"
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format, *args):  # noqa: A003
            return

    httpd = HTTPServer(("127.0.0.1", 0), Handler)
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ctx.load_cert_chain(str(cert_path), str(key_path))
    httpd.socket = ctx.wrap_socket(httpd.socket, server_side=True)
    port = httpd.server_address[1]
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()

    verify = ssl.create_default_context(cafile=str(cert_path))
    try:
        async with httpx.AsyncClient(verify=verify) as client:
            result = await fetch_url(
                client, f"https://{hostname}:{port}/page", timeout_s=3.0
            )
    finally:
        httpd.shutdown()

    assert result.error is None, result.error
    assert result.status_code == 200
    assert result.text and "pinned-ok" in result.text
    assert seen_host_header, "server should have received a request"
    assert seen_host_header[0].startswith(hostname)


def test_validate_url_for_fetch_returns_ips(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "socket.getaddrinfo",
        lambda host, *a, **k: _gai(PUBLIC_V4),
    )
    target = validate_url_for_fetch("https://example.com/a?b=1")
    assert target.hostname == "example.com"
    assert target.validated_ips == (PUBLIC_V4,)
    assert target.url.startswith("https://example.com/")
    pinned = pinned_connect_url(target, PUBLIC_V4)
    assert urlparse(pinned).hostname == PUBLIC_V4
    assert request_extensions_for_pin(target) == {"sni_hostname": "example.com"}


def test_pinned_connect_url_rejects_foreign_ip(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "socket.getaddrinfo",
        lambda host, *a, **k: _gai(PUBLIC_V4),
    )
    target = validate_url_for_fetch("https://example.com/")
    with pytest.raises(SSRFError):
        pinned_connect_url(target, "127.0.0.1")


@pytest.mark.asyncio
async def test_fetch_pin_sets_host_and_sni(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "socket.getaddrinfo",
        lambda host, *a, **k: _gai(PUBLIC_V4),
    )
    captured: dict = {}

    async def fake_get(url, **kwargs):  # noqa: ANN001
        captured["url"] = str(url)
        captured["headers"] = kwargs.get("headers")
        captured["extensions"] = kwargs.get("extensions")
        resp = MagicMock()
        resp.status_code = 200
        resp.headers = {"content-type": "text/html"}
        resp.url = url
        resp.text = "<html></html>"
        return resp

    client = MagicMock()
    client.get = AsyncMock(side_effect=fake_get)
    result = await fetch_url(client, "https://example.com/x")
    assert result.error is None
    assert urlparse(captured["url"]).hostname == PUBLIC_V4
    assert captured["headers"]["Host"] == "example.com"
    assert captured["extensions"]["sni_hostname"] == "example.com"
