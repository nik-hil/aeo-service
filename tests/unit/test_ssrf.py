"""Unit tests for SSRF URL allow-policy."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from aeo_mvp.security.ssrf import (
    SSRFError,
    assert_safe_public_url,
    is_obviously_unsafe_url,
)


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


@pytest.mark.asyncio
async def test_fetch_url_blocks_redirect_to_private(monkeypatch: pytest.MonkeyPatch) -> None:
    import httpx

    from aeo_mvp.crawler.fetch import fetch_url

    public_host = "example.com"

    def fake_getaddrinfo(host, *args, **kwargs):  # noqa: ANN001
        if host in {"127.0.0.1", "localhost"} or str(host).startswith("127."):
            return [(2, 1, 6, "", ("127.0.0.1", 0))]
        return [(2, 1, 6, "", ("93.184.216.34", 0))]

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
