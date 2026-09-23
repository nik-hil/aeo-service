"""Env / config contract tests."""

from aeo_mvp.config import Settings, get_settings


def test_llm_env_names_only():
    get_settings.cache_clear()
    s = Settings(
        llm_api_key="k",
        llm_base_url="https://inference.do-ai.run/v1",
        llm_model="openai-gpt-5.6-luna",
        api_key="service",
    )
    assert s.llm_api_key == "k"
    assert s.api_key == "service"
    assert not hasattr(s, "openai_api_key")
    assert not hasattr(s, "do_model_access_key")
    assert not hasattr(s, "perplexity_api_key")
    assert s.llm_model == "openai-gpt-5.6-luna"


def test_default_model_is_luna_candidate():
    get_settings.cache_clear()
    s = Settings(llm_api_key=None)
    assert s.llm_model == "openai-gpt-5.6-luna"
