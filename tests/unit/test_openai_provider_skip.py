"""OpenAI provider construction without API key fails closed (P0-4)."""

import pytest

from aeo_mvp.visibility.openai_compatible import (
    OpenAICompatibleError,
    OpenAICompatibleProvider,
)


def test_openai_provider_requires_key(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    from aeo_mvp.config import get_settings

    get_settings.cache_clear()
    with pytest.raises(OpenAICompatibleError) as ei:
        OpenAICompatibleProvider(api_key=None)
    assert ei.value.category == "missing_credentials"
