"""Workstream C / P1-12: LLM detect_citation uses TargetSiteIdentity / target_match.

Same domain-match-v1 rules as AI-search DO. Does not loosen AI-search matching.
Preserves P0 visibility/DO/SSRF contracts. No live DO / Hashnode.
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from aeo_mvp.config import Settings, get_settings
from aeo_mvp.target_site import resolve_target_site_identity, target_match
from aeo_mvp.visibility.base import VisibilityContext
from aeo_mvp.visibility.metrics import detect_citation
from aeo_mvp.visibility.openai_compatible import OpenAICompatibleProvider


HASHNODE_SEED = "https://nik-hil.hashnode.dev/agents-zero-to-hero"
ORDINARY_SEED = "https://www.example.com/about"
FAKE_KEY = "sk-test-fake-key-not-real-ABCDEFGH"


def _hashnode_identity():
    return resolve_target_site_identity(HASHNODE_SEED)


def _ordinary_identity():
    return resolve_target_site_identity(ORDINARY_SEED)


def _llm_context(*, base_url: str, site_registrable_domain: str) -> VisibilityContext:
    ident = resolve_target_site_identity(base_url)
    return VisibilityContext(
        job_id="job-p1-12",
        base_url=base_url,
        brand_tokens=["Nik"],
        site_registrable_domain=site_registrable_domain,
        prompt_id="p1",
        run_index=0,
        target_hostname=ident.hostname,
        target_origin=ident.origin,
        target_domain_scope=ident.target_domain_scope,
        multi_tenant_host=ident.multi_tenant_host,
        match_rule_version=ident.match_rule_version,
        target_site=ident.to_audit_dict(),
    )


def _ok_completion(content: str) -> dict:
    return {
        "id": "chatcmpl-test",
        "choices": [{"message": {"role": "assistant", "content": content}}],
        "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
    }


def _mock_client(resp: MagicMock) -> AsyncMock:
    mock_client = AsyncMock()
    mock_client.__aenter__.return_value = mock_client
    mock_client.__aexit__.return_value = None
    mock_client.post = AsyncMock(return_value=resp)
    return mock_client


def _http_resp(*, json_data: dict) -> MagicMock:
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = json_data
    return mock_resp


def _iso_settings(monkeypatch) -> Settings:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    get_settings.cache_clear()
    isolated = Settings(_env_file=None, OPENAI_API_KEY=FAKE_KEY)
    monkeypatch.setattr(
        "aeo_mvp.visibility.openai_compatible.get_settings",
        lambda: isolated,
    )
    return isolated


# --- P1-12 detect_citation matrix (hostname-scoped multi-tenant) ---


@pytest.mark.parametrize(
    "url,expect",
    [
        ("https://nik-hil.hashnode.dev/article", True),  # exact hostname
        ("https://www.nik-hil.hashnode.dev/x", True),  # www alias
        ("https://other-user.hashnode.dev/post", False),  # sibling tenant
        ("https://other.hashnode.dev/x", False),  # sibling tenant
        ("https://hashnode.dev/", False),  # platform apex
        ("https://www.hashnode.dev/", False),  # www apex
        ("https://maliciousnik-hil.hashnode.dev/", False),  # lookalike
        ("https://evil-nik-hil.hashnode.dev/", False),  # lookalike
        ("https://nik-hil.hashnode.dev.evil.com/", False),  # suffix lookalike
    ],
)
def test_p1_12_detect_citation_hashnode_hostname_scope(url, expect):
    ident = _hashnode_identity()
    assert ident.target_domain_scope == "hostname"
    assert ident.registrable_domain == "hashnode.dev"
    text = f"See {url} for details."
    cited, urls = detect_citation(text, ident)
    assert cited is expect
    if expect:
        assert url in urls
    else:
        assert urls == []
    # Same outcome as AI-search target_match (no rule drift).
    assert target_match(url, ident) is expect


def test_p1_12_bare_psl_string_must_not_be_used_for_tenant_jobs():
    """Audit failure mode: detect_citation(..., 'hashnode.dev') credits siblings."""
    sibling_text = "See https://other.hashnode.dev/x"
    ident = _hashnode_identity()
    cited, _ = detect_citation(sibling_text, ident)
    assert cited is False

    # Bare platform apex string resolves as platform_apex — still matches siblings.
    # That is why openai_compatible must resolve identity from base_url, not apex.
    legacy, _ = detect_citation(sibling_text, "hashnode.dev")
    assert legacy is True
    apex_ident = resolve_target_site_identity("hashnode.dev")
    assert apex_ident.identity_kind == "platform_apex"


@pytest.mark.parametrize(
    "url,expect",
    [
        ("https://example.com/a", True),
        ("https://www.example.com/a", True),
        ("https://blog.example.com/a", True),  # ordinary registrable subdomain
        ("https://malicious-example.com/a", False),
        ("https://example.com.evil.org/a", False),
    ],
)
def test_p1_12_detect_citation_ordinary_registrable(url, expect):
    ident = _ordinary_identity()
    assert ident.target_domain_scope == "registrable_domain"
    cited, urls = detect_citation(f"See {url}", ident)
    assert cited is expect
    assert target_match(url, ident) is expect
    if expect:
        assert url in urls


def test_p1_12_detect_citation_string_seed_url_resolves_identity():
    """Passing the seed URL string (not apex) is equivalent to frozen identity."""
    text = "https://other-user.hashnode.dev/x and https://nik-hil.hashnode.dev/ok"
    cited, urls = detect_citation(text, HASHNODE_SEED)
    assert cited is True
    assert urls == ["https://nik-hil.hashnode.dev/ok"]


def test_p1_12_detect_citation_identity_kwarg():
    ident = _hashnode_identity()
    cited, urls = detect_citation(
        "https://nik-hil.hashnode.dev/a",
        "ignored.hashnode.dev",
        identity=ident,
    )
    assert cited is True
    assert urls == ["https://nik-hil.hashnode.dev/a"]


def test_p1_12_ai_search_target_match_unchanged_sibling_rejected():
    """Do not loosen AI-search hostname scope while fixing LLM citation."""
    ident = _hashnode_identity()
    assert not target_match("https://other-user.hashnode.dev/x", ident)
    assert not target_match("https://hashnode.dev/", ident)
    assert target_match("https://nik-hil.hashnode.dev/x", ident)


# --- openai_compatible wires base_url identity, not site_registrable_domain ---


@pytest.mark.asyncio
async def test_p1_12_openai_provider_rejects_sibling_and_apex(monkeypatch):
    _iso_settings(monkeypatch)
    content = (
        "Nik writes well. See https://other-user.hashnode.dev/post "
        "and https://hashnode.dev/docs for more."
    )
    resp = _http_resp(json_data=_ok_completion(content))
    ctx = _llm_context(
        base_url=HASHNODE_SEED,
        site_registrable_domain="hashnode.dev",  # legacy apex — must not drive match
    )
    with patch(
        "aeo_mvp.visibility.openai_compatible.httpx.AsyncClient",
        return_value=_mock_client(resp),
    ):
        obs = await OpenAICompatibleProvider(api_key=FAKE_KEY).run_query(
            "who writes about agents?", context=ctx
        )
    assert obs.detected_citation is False
    assert obs.cited_urls == []
    assert "domain-match-v1" in obs.extraction_methodology
    assert isinstance(obs.observed_at, datetime)
    assert obs.observed_at.tzinfo is not None or obs.observed_at.replace(
        tzinfo=timezone.utc
    )


@pytest.mark.asyncio
async def test_p1_12_openai_provider_credits_exact_and_www_hostname(monkeypatch):
    _iso_settings(monkeypatch)
    content = (
        "Details at https://nik-hil.hashnode.dev/article and "
        "https://www.nik-hil.hashnode.dev/mirror"
    )
    resp = _http_resp(json_data=_ok_completion(content))
    ctx = _llm_context(
        base_url=HASHNODE_SEED,
        site_registrable_domain="hashnode.dev",
    )
    with patch(
        "aeo_mvp.visibility.openai_compatible.httpx.AsyncClient",
        return_value=_mock_client(resp),
    ):
        obs = await OpenAICompatibleProvider(api_key=FAKE_KEY).run_query(
            "nik hil blog?", context=ctx
        )
    assert obs.detected_citation is True
    assert "https://nik-hil.hashnode.dev/article" in obs.cited_urls
    assert "https://www.nik-hil.hashnode.dev/mirror" in obs.cited_urls


@pytest.mark.asyncio
async def test_p1_12_openai_provider_ordinary_registrable(monkeypatch):
    _iso_settings(monkeypatch)
    content = "See https://blog.example.com/guide and https://malicious-example.com/x"
    resp = _http_resp(json_data=_ok_completion(content))
    ctx = _llm_context(
        base_url=ORDINARY_SEED,
        site_registrable_domain="example.com",
    )
    with patch(
        "aeo_mvp.visibility.openai_compatible.httpx.AsyncClient",
        return_value=_mock_client(resp),
    ):
        obs = await OpenAICompatibleProvider(api_key=FAKE_KEY).run_query(
            "example guide?", context=ctx
        )
    assert obs.detected_citation is True
    assert obs.cited_urls == ["https://blog.example.com/guide"]
