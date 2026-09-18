"""Pydantic request/response schemas."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, HttpUrl, field_validator


class JobOptions(BaseModel):
    max_pages: int = Field(default=25, ge=1, le=25)
    max_depth: int = Field(default=2, ge=0, le=2)
    runs_per_prompt: int = Field(default=3, ge=1, le=5)
    provider: Literal["auto", "demo", "openai_compatible"] = "auto"
    category: str | None = None


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
