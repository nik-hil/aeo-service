"""Live provider skips cleanly without API key."""

import pytest

from aeo_mvp.visibility.openai_compatible import OpenAICompatibleProvider


def test_openai_provider_requires_key(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    from aeo_mvp.config import get_settings

    get_settings.cache_clear()
    with pytest.raises(ValueError, match="OPENAI_API_KEY"):
        OpenAICompatibleProvider(api_key=None)
