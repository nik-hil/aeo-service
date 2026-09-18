"""AIVisibilityProvider protocol and DTOs."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal, Protocol, runtime_checkable

from pydantic import BaseModel, Field


class VisibilityContext(BaseModel):
    job_id: str
    base_url: str
    brand_tokens: list[str]
    site_registrable_domain: str
    prompt_id: str
    run_index: int
    protocol_version: str = "vis-exp-v1"


class VisibilityObservation(BaseModel):
    provider_name: str
    engine_label: str
    query: str
    prompt_id: str
    run_index: int
    observed_at: datetime
    raw_response: str | None
    raw_storage_permitted: bool = True
    detected_mention: bool
    detected_citation: bool
    cited_urls: list[str] = Field(default_factory=list)
    extraction_methodology: str
    provenance: Literal["api_observation", "synthetic_demo", "estimate"]
    meta: dict[str, Any] = Field(default_factory=dict)


@runtime_checkable
class AIVisibilityProvider(Protocol):
    name: str

    async def run_query(
        self, query: str, *, context: VisibilityContext
    ) -> VisibilityObservation: ...
