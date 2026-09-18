"""Settings loaded from environment (no side effects beyond env read)."""

from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

USER_AGENT = "AEOBot/0.1 (+research; respectful)"
HEALTH_FORMULA_VERSION = "health-v1"
EXPERIMENT_PROTOCOL_VERSION = "llm-mention-v1"
LLM_MENTION_PROTOCOL_VERSION = "llm-mention-v1"
AI_SEARCH_PROTOCOL_VERSION = "ai-search-vis-v1"
PROMPT_SET_ID = "prompt-set-v1"
REC_CATALOG_VERSION = "rec-catalog-v1"
DEMO_BASE_URL = "https://demo.example/"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    demo_mode: bool = Field(default=False, alias="AEO_DEMO_MODE")
    database_url: str = Field(default="sqlite:///./aeo_mvp.db", alias="AEO_DATABASE_URL")
    openai_api_key: str | None = Field(default=None, alias="OPENAI_API_KEY")
    openai_base_url: str = Field(default="https://api.openai.com/v1", alias="OPENAI_BASE_URL")
    openai_model: str = Field(default="gpt-4o-mini", alias="OPENAI_MODEL")
    crawl_max_pages: int = Field(default=25, alias="AEO_CRAWL_MAX_PAGES")
    crawl_max_depth: int = Field(default=2, alias="AEO_CRAWL_MAX_DEPTH")
    crawl_timeout_s: float = Field(default=5.0, alias="AEO_CRAWL_TIMEOUT_S")
    query_top_n: int = Field(default=20, alias="AEO_QUERY_TOP_N")
    # Paid DO web_search never auto-runs from discovery; requires explicit opt-in.
    paid_retrieval_opt_in: bool = Field(default=False, alias="AEO_PAID_RETRIEVAL_OPT_IN")
    site_understanding_llm: bool = Field(default=False, alias="AEO_SITE_UNDERSTANDING_LLM")
    perplexity_api_key: str | None = Field(default=None, alias="PERPLEXITY_API_KEY")

    # Visibility provider selection: auto | demo | openai_compatible | digitalocean_web_search
    visibility_provider: str = Field(default="auto", alias="AEO_VISIBILITY_PROVIDER")

    # DigitalOcean Inference (Responses API + web_search)
    do_model_access_key: str | None = Field(default=None, alias="DO_MODEL_ACCESS_KEY")
    model_access_key: str | None = Field(
        default=None,
        alias="MODEL_ACCESS_KEY",
        description="Fallback for DO docs naming; prefer DO_MODEL_ACCESS_KEY",
    )
    do_inference_base_url: str = Field(
        default="https://inference.do-ai.run/v1",
        alias="DO_INFERENCE_BASE_URL",
    )
    do_inference_model: str = Field(
        default="openai-gpt-4o",
        alias="DO_INFERENCE_MODEL",
    )
    do_web_search_max_uses: int = Field(default=3, alias="DO_WEB_SEARCH_MAX_USES")
    do_web_search_max_results: int = Field(default=5, alias="DO_WEB_SEARCH_MAX_RESULTS")
    do_inference_timeout_s: float = Field(default=60.0, alias="DO_INFERENCE_TIMEOUT_S")

    @property
    def user_agent(self) -> str:
        return USER_AGENT

    @property
    def effective_do_api_key(self) -> str | None:
        return self.do_model_access_key or self.model_access_key


@lru_cache
def get_settings() -> Settings:
    return Settings()
