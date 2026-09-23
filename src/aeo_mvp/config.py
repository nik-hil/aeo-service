"""Settings from environment. Single LLM credential + separate API auth."""

from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# Experiment defaults (DO Inference catalog):
#   AEO_LLM_MODEL=openai-gpt-6-astra      (default after CoS live acceptance)
#   AEO_LLM_MODEL=openai-gpt-5.6-luna     (concise compare)
# See docs/MODELS.md. Never hardcode secrets.


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
    )

    llm_api_key: str | None = Field(default=None, alias="AEO_LLM_API_KEY")
    llm_base_url: str = Field(
        default="https://inference.do-ai.run/v1",
        alias="AEO_LLM_BASE_URL",
    )
    llm_model: str = Field(
        default="openai-gpt-6-astra",
        alias="AEO_LLM_MODEL",
    )
    llm_timeout_s: float = Field(default=120.0, alias="AEO_LLM_TIMEOUT_S")
    web_search_max_uses: int = Field(default=3, alias="AEO_WEB_SEARCH_MAX_USES")
    web_search_max_results: int = Field(default=5, alias="AEO_WEB_SEARCH_MAX_RESULTS")

    api_key: str | None = Field(default=None, alias="AEO_API_KEY")

    live_retrieval_test: bool = Field(default=False, alias="AEO_LIVE_RETRIEVAL_TEST")


@lru_cache
def get_settings() -> Settings:
    return Settings()
