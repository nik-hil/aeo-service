"""Settings loaded from environment (no side effects beyond env read)."""

from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

USER_AGENT = "AEOBot/0.1 (+research; respectful)"
HEALTH_FORMULA_VERSION = "health-v1"
EXPERIMENT_PROTOCOL_VERSION = "vis-exp-v1"
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

    @property
    def user_agent(self) -> str:
        return USER_AGENT


@lru_cache
def get_settings() -> Settings:
    return Settings()
