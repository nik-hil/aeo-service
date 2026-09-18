"""PSL-based registrable_domain and DigitalOcean web_search provider tests."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from aeo_mvp.domains import registrable_domain
from aeo_mvp.visibility.base import VisibilityContext
from aeo_mvp.visibility.digitalocean_web_search import (
    DigitalOceanWebSearchError,
    DigitalOceanWebSearchProvider,
    _parse_responses_output,
)
from aeo_mvp.visibility.metrics import (
    aggregate_ai_search_metrics,
    domain_matches_target,
)


def test_registrable_domain_basic():
    assert registrable_domain("example.com") == "example.com"
    assert registrable_domain("https://www.example.com/path") == "example.com"
    assert registrable_domain("blog.example.com") == "example.com"
    assert registrable_domain("https://blog.example.com/x") == "example.com"


def test_registrable_domain_multi_part_tld():
    assert registrable_domain("example.co.uk") == "example.co.uk"
    assert registrable_domain("https://www.shop.example.co.uk/a") == "example.co.uk"


def test_registrable_domain_lookalike_not_equal():
    assert registrable_domain("malicious-example.com") == "malicious-example.com"
    assert registrable_domain("malicious-example.com") != registrable_domain(
        "example.com"
    )
    assert not domain_matches_target(
        "https://malicious-example.com/page", "example.com"
    )
    assert domain_matches_target("https://blog.example.com/x", "www.example.com")


def test_registrable_domain_demo_fixture_host():
    # Unrecognized / special hosts keep full label (minus www.)
    assert registrable_domain("https://demo.example/") == "demo.example"


SAMPLE_DO_RESPONSE = {
    "id": "resp_test",
    "output": [
        {
            "type": "web_search_call",
            "status": "completed",
            "id": "ws_call_1",
            "action": {
                "type": "search",
                "queries": ["Hashnode blogging platform"],
                "query": "Hashnode blogging platform",
                "sources": [
                    {"url": "https://hashnode.com/"},
                    {"url": "https://blog.hashnode.com/features"},
                    {"url": "https://malicious-hashnode.com/fake"},
                ],
            },
        },
        {
            "type": "message",
            "content": [
                {
                    "type": "output_text",
                    "text": (
                        "Hashnode is a blogging platform for developers. "
                        "See https://other.example/docs for unrelated notes."
                    ),
                    "annotations": [
                        {
                            "type": "url_citation",
                            "url": "https://hashnode.com/about",
                            "title": "About Hashnode",
                            "start_index": 0,
                            "end_index": 40,
                        },
                        {
                            "type": "url_citation",
                            "url": "https://malicious-hashnode.com/spoof",
                            "title": "Spoof",
                            "start_index": 41,
                            "end_index": 50,
                        },
                    ],
                }
            ],
        },
    ],
}


SAMPLE_APPEAR_NOT_CITED = {
    "id": "resp_appear",
    "output": [
        {
            "type": "web_search_call",
            "status": "completed",
            "action": {
                "queries": ["example blog"],
                "sources": [
                    {"url": "https://www.example.com/post"},
                    {"url": "https://competitor.com/"},
                ],
            },
        },
        {
            "type": "message",
            "content": [
                {
                    "type": "output_text",
                    "text": "Several blogs cover this topic.",
                    "annotations": [
                        {
                            "type": "url_citation",
                            "url": "https://competitor.com/article",
                            "title": "Competitor",
                            "start_index": 0,
                            "end_index": 10,
                        }
                    ],
                }
            ],
        },
    ],
}


def _ctx(**kwargs) -> VisibilityContext:
    base = dict(
        job_id="j1",
        base_url="https://hashnode.com/",
        brand_tokens=["Hashnode"],
        site_registrable_domain="hashnode.com",
        prompt_id="dq1",
        run_index=0,
        protocol_version="ai-search-vis-v1",
    )
    base.update(kwargs)
    return VisibilityContext(**base)


def test_parse_responses_flexible_fields():
    parsed = _parse_responses_output(SAMPLE_DO_RESPONSE)
    assert "Hashnode blogging platform" in parsed["search_queries"]
    assert "https://hashnode.com/" in parsed["source_urls"]
    assert any(c["url"] == "https://hashnode.com/about" for c in parsed["citations"])
    assert "Hashnode is a blogging platform" in (parsed["answer_text"] or "")


def test_parse_query_singular_only():
    data = {
        "output": [
            {
                "type": "web_search_call",
                "action": {"query": "solo query", "type": "search"},
            },
            {
                "type": "message",
                "content": [{"type": "output_text", "text": "ok", "annotations": []}],
            },
        ]
    }
    parsed = _parse_responses_output(data)
    assert parsed["search_queries"] == ["solo query"]


def test_provider_requires_key(monkeypatch):
    monkeypatch.delenv("DO_MODEL_ACCESS_KEY", raising=False)
    monkeypatch.delenv("MODEL_ACCESS_KEY", raising=False)
    from aeo_mvp.config import get_settings

    get_settings.cache_clear()
    with pytest.raises(DigitalOceanWebSearchError, match="DO_MODEL_ACCESS_KEY"):
        DigitalOceanWebSearchProvider(api_key=None)
    get_settings.cache_clear()


@pytest.mark.asyncio
async def test_successful_cite_of_target(monkeypatch):
    monkeypatch.setenv("DO_MODEL_ACCESS_KEY", "test-key-not-real")
    from aeo_mvp.config import get_settings

    get_settings.cache_clear()

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = SAMPLE_DO_RESPONSE
    mock_resp.text = json.dumps(SAMPLE_DO_RESPONSE)

    mock_client = AsyncMock()
    mock_client.__aenter__.return_value = mock_client
    mock_client.__aexit__.return_value = None
    mock_client.post = AsyncMock(return_value=mock_resp)

    with patch("aeo_mvp.visibility.digitalocean_web_search.httpx.AsyncClient", return_value=mock_client):
        p = DigitalOceanWebSearchProvider(api_key="test-key-not-real")
        obs = await p.run_query("What is Hashnode?", context=_ctx())

    assert obs.retrieval_enabled is True
    assert obs.experiment_kind == "ai_search_visibility"
    assert obs.provenance == "api_observation"
    assert p.capabilities.retrieval_enabled is True
    assert p.capabilities.measures_consumer_ui is False
    assert obs.target_domain_cited is True
    assert obs.target_domain_appeared is True
    assert obs.detected_mention is True
    assert any("hashnode.com" in u for u in obs.cited_urls)
    assert "Authorization" not in (obs.raw_response or "")
    assert "test-key-not-real" not in (obs.raw_response or "")
    assert obs.search_queries
    get_settings.cache_clear()


@pytest.mark.asyncio
async def test_appear_in_sources_but_not_cited(monkeypatch):
    monkeypatch.setenv("DO_MODEL_ACCESS_KEY", "test-key-not-real")
    from aeo_mvp.config import get_settings

    get_settings.cache_clear()

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = SAMPLE_APPEAR_NOT_CITED
    mock_resp.text = json.dumps(SAMPLE_APPEAR_NOT_CITED)

    mock_client = AsyncMock()
    mock_client.__aenter__.return_value = mock_client
    mock_client.__aexit__.return_value = None
    mock_client.post = AsyncMock(return_value=mock_resp)

    with patch("aeo_mvp.visibility.digitalocean_web_search.httpx.AsyncClient", return_value=mock_client):
        p = DigitalOceanWebSearchProvider(api_key="test-key-not-real")
        obs = await p.run_query(
            "example blogs",
            context=_ctx(
                base_url="https://example.com/",
                brand_tokens=["Example"],
                site_registrable_domain="example.com",
            ),
        )

    assert obs.target_domain_appeared is True
    assert obs.target_domain_cited is False
    assert obs.cited_urls == []
    get_settings.cache_clear()


@pytest.mark.asyncio
async def test_lookalike_domain_not_counted_as_cite(monkeypatch):
    monkeypatch.setenv("DO_MODEL_ACCESS_KEY", "test-key-not-real")
    from aeo_mvp.config import get_settings

    get_settings.cache_clear()

    data = {
        "output": [
            {
                "type": "web_search_call",
                "action": {
                    "queries": ["example"],
                    "sources": [{"url": "https://malicious-example.com/x"}],
                },
            },
            {
                "type": "message",
                "content": [
                    {
                        "type": "output_text",
                        "text": "A site exists.",
                        "annotations": [
                            {
                                "type": "url_citation",
                                "url": "https://malicious-example.com/x",
                                "title": "Fake",
                                "start_index": 0,
                                "end_index": 5,
                            }
                        ],
                    }
                ],
            },
        ]
    }
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = data
    mock_resp.text = json.dumps(data)

    mock_client = AsyncMock()
    mock_client.__aenter__.return_value = mock_client
    mock_client.__aexit__.return_value = None
    mock_client.post = AsyncMock(return_value=mock_resp)

    with patch("aeo_mvp.visibility.digitalocean_web_search.httpx.AsyncClient", return_value=mock_client):
        p = DigitalOceanWebSearchProvider(api_key="test-key-not-real")
        obs = await p.run_query(
            "example",
            context=_ctx(
                base_url="https://example.com/",
                brand_tokens=["ExampleCo"],
                site_registrable_domain="example.com",
            ),
        )

    assert obs.target_domain_appeared is False
    assert obs.target_domain_cited is False
    get_settings.cache_clear()


@pytest.mark.asyncio
async def test_http_error_raises_explicitly(monkeypatch):
    monkeypatch.setenv("DO_MODEL_ACCESS_KEY", "test-key-not-real")
    from aeo_mvp.config import get_settings

    get_settings.cache_clear()

    mock_resp = MagicMock()
    mock_resp.status_code = 401
    mock_resp.text = "unauthorized"

    mock_client = AsyncMock()
    mock_client.__aenter__.return_value = mock_client
    mock_client.__aexit__.return_value = None
    mock_client.post = AsyncMock(return_value=mock_resp)

    with patch("aeo_mvp.visibility.digitalocean_web_search.httpx.AsyncClient", return_value=mock_client):
        p = DigitalOceanWebSearchProvider(api_key="test-key-not-real")
        with pytest.raises(DigitalOceanWebSearchError, match="HTTP 401"):
            await p.run_query("q", context=_ctx())
    get_settings.cache_clear()


@pytest.mark.asyncio
async def test_no_web_search_output_raises(monkeypatch):
    monkeypatch.setenv("DO_MODEL_ACCESS_KEY", "test-key-not-real")
    from aeo_mvp.config import get_settings

    get_settings.cache_clear()

    data = {
        "output": [
            {
                "type": "message",
                "content": [
                    {"type": "output_text", "text": "I cannot search.", "annotations": []}
                ],
            }
        ]
    }
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = data
    mock_resp.text = json.dumps(data)

    mock_client = AsyncMock()
    mock_client.__aenter__.return_value = mock_client
    mock_client.__aexit__.return_value = None
    mock_client.post = AsyncMock(return_value=mock_resp)

    with patch("aeo_mvp.visibility.digitalocean_web_search.httpx.AsyncClient", return_value=mock_client):
        p = DigitalOceanWebSearchProvider(api_key="test-key-not-real")
        with pytest.raises(DigitalOceanWebSearchError, match="web_search"):
            await p.run_query("q", context=_ctx())
    get_settings.cache_clear()


def test_ai_search_aggregate_rates_separate_from_llm():
    from aeo_mvp.visibility.base import VisibilityObservation

    obs = [
        VisibilityObservation(
            provider_name="digitalocean_web_search",
            engine_label="digitalocean_web_search:openai-gpt-4o",
            query="q1",
            prompt_id="p1",
            run_index=0,
            observed_at=datetime(2026, 9, 18, tzinfo=timezone.utc),
            raw_response="{}",
            detected_mention=True,
            detected_citation=True,
            cited_urls=["https://example.com/"],
            extraction_methodology="ai-search-vis-v1",
            provenance="api_observation",
            retrieval_enabled=True,
            experiment_kind="ai_search_visibility",
            target_domain_appeared=True,
            target_domain_cited=True,
            source_urls=["https://example.com/"],
            search_queries=["q1"],
            model_id="openai-gpt-4o",
        ),
        VisibilityObservation(
            provider_name="digitalocean_web_search",
            engine_label="digitalocean_web_search:openai-gpt-4o",
            query="q2",
            prompt_id="p2",
            run_index=0,
            observed_at=datetime(2026, 9, 18, tzinfo=timezone.utc),
            raw_response="{}",
            detected_mention=False,
            detected_citation=False,
            cited_urls=[],
            extraction_methodology="ai-search-vis-v1",
            provenance="api_observation",
            retrieval_enabled=True,
            experiment_kind="ai_search_visibility",
            target_domain_appeared=True,
            target_domain_cited=False,
            source_urls=["https://example.com/x"],
            search_queries=["q2"],
            model_id="openai-gpt-4o",
        ),
    ]
    rates = aggregate_ai_search_metrics(obs)
    assert rates.ai_search_mention_rate == 0.5
    assert rates.ai_search_citation_rate == 0.5
    assert rates.target_domain_appearance_rate == 1.0
    assert rates.query_coverage == 1.0  # both prompts covered via mention/appearance


@pytest.mark.asyncio
@pytest.mark.skipif(
    not (
        (os.environ.get("DO_MODEL_ACCESS_KEY") or os.environ.get("MODEL_ACCESS_KEY"))
        and os.environ.get("AEO_LIVE_RETRIEVAL_TEST", "").lower() == "true"
    ),
    reason="Live DO retrieval test requires DO_MODEL_ACCESS_KEY and AEO_LIVE_RETRIEVAL_TEST=true",
)
async def test_live_digitalocean_web_search_optional():
    from aeo_mvp.config import get_settings

    get_settings.cache_clear()
    p = DigitalOceanWebSearchProvider()
    obs = await p.run_query(
        "What is DigitalOcean?",
        context=_ctx(
            base_url="https://www.digitalocean.com/",
            brand_tokens=["DigitalOcean"],
            site_registrable_domain="digitalocean.com",
        ),
    )
    assert obs.retrieval_enabled is True
    assert obs.provenance == "api_observation"
    assert obs.search_queries or obs.source_urls or obs.meta.get("citations")
    # Never leak key into stored raw
    key = os.environ.get("DO_MODEL_ACCESS_KEY") or os.environ.get("MODEL_ACCESS_KEY")
    assert key not in (obs.raw_response or "")
    get_settings.cache_clear()
