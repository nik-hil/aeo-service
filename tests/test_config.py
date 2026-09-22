"""Env / config contract tests."""

from aeo_mvp.config import Settings, get_settings


def test_llm_env_names_only():
    get_settings.cache_clear()
    s = Settings(
        llm_api_key="k",
        llm_base_url="https://inference.do-ai.run/v1",
        llm_model="openai-gpt-4o",
        api_key="service",
    )
    assert s.llm_api_key == "k"
    assert s.api_key == "service"
    # Legacy names are not Settings fields.
    assert not hasattr(s, "openai_api_key")
    assert not hasattr(s, "do_model_access_key")
    assert not hasattr(s, "perplexity_api_key")
    assert s.llm_base_url == "https://inference.do-ai.run/v1"
    assert s.llm_model == "openai-gpt-4o"
