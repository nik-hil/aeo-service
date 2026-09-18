"""Pydantic request/response schemas."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class JobOptions(BaseModel):
    """Job options. Extra keys are preserved for Phase 4 discovery / seeds."""

    model_config = ConfigDict(extra="allow")

    max_pages: int = Field(default=25, ge=1, le=25)
    max_depth: int = Field(default=2, ge=0, le=2)
    runs_per_prompt: int = Field(default=3, ge=1, le=5)
    provider: Literal[
        "auto", "demo", "openai_compatible", "digitalocean_web_search", "digitalocean"
    ] = "auto"
    category: str | None = None
    # Phase 4 query intelligence
    selection_seed: int | str | None = None
    query_selection_seed: int | str | None = None
    experiment_seed: int | str | None = None
    query_discovery_version: Literal["v1", "v2", "query-discovery-v1", "query-discovery-v2"] | None = (
        "v2"
    )
    discovery_only: bool = False
    dry_run: bool = False
    paid_retrieval_opt_in: bool = False
    query_top_n: int | None = Field(default=None, ge=8, le=30)
    semantic_dedup: Literal["lexical", "simhash", "simhash_v1"] | None = "lexical"
    mmr_lambda: float | None = None
    max_per_topic: int | None = None


class CreateJobRequest(BaseModel):
    url: str
    demo_mode: bool = False
    options: JobOptions | None = None

    @field_validator("url")
    @classmethod
    def validate_url(cls, v: str) -> str:
        v = (v or "").strip()
        if not v.startswith(("http://", "https://")):
            raise ValueError("url must be http(s)")
        return v


class JobLinks(BaseModel):
    self: str
    report: str
    pages: str


class JobCreatedResponse(BaseModel):
    id: str
    base_url: str
    status: str
    demo_mode: bool
    created_at: str
    links: JobLinks


class JobStatusResponse(BaseModel):
    id: str
    base_url: str
    status: str
    demo_mode: bool
    error_message: str | None = None
    health_score: float | None = None
    health_formula_version: str | None = None
    experiment_protocol_version: str | None = None
    component_scores: dict[str, float] | None = None
    created_at: str
    updated_at: str
    completed_at: str | None = None


class PageItem(BaseModel):
    id: str
    url: str
    final_url: str | None = None
    depth: int
    status_code: int | None = None
    title: str | None = None
    fetch_error: str | None = None


class PagesResponse(BaseModel):
    job_id: str
    count: int
    pages: list[PageItem]


class HealthResponse(BaseModel):
    status: Literal["ok"] = "ok"


class ErrorResponse(BaseModel):
    detail: str


class ContentOptimizationRequest(BaseModel):
    """Grounded optimization input — not a free-form topic generator.

    Provide one of:
    - ``job_id`` (+ optional ``page_id``) to reuse crawled HTML / queryset
    - ``source_url`` (SSRF-validated live fetch)
    - ``html`` (+ optional ``url``) for offline / fixture analysis
    """

    model_config = ConfigDict(extra="forbid")

    job_id: str | None = None
    page_id: str | None = None
    source_url: str | None = None
    html: str | None = None
    url: str | None = None
    queryset: dict[str, Any] | list[Any] | None = None
    site_profile: dict[str, Any] | None = None
    config: dict[str, Any] | None = None
    paid_llm_opt_in: bool = False

    @field_validator("source_url", "url")
    @classmethod
    def validate_optional_url(cls, v: str | None) -> str | None:
        if v is None:
            return v
        v = v.strip()
        if not v.startswith(("http://", "https://")):
            raise ValueError("url must be http(s)")
        return v


class ContentOptimizationResponse(BaseModel):
    model_config = ConfigDict(extra="allow")

    page_intelligence: dict[str, Any]
    gap_report: dict[str, Any]
    brief: dict[str, Any]
    draft: dict[str, Any]
    paid_retrieval: bool = False
    paid_llm: bool = False
