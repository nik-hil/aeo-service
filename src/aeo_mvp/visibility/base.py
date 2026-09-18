"""AIVisibilityProvider protocol and DTOs."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal, Protocol, runtime_checkable

from pydantic import BaseModel, Field

ExperimentKind = Literal["llm_mention", "ai_search_visibility"]


class ProviderCapabilities(BaseModel):
    """Declared capabilities of a visibility provider (D021)."""

    provider_id: str
    retrieval_enabled: bool
    experiment_kinds: list[ExperimentKind]
    returns_search_queries: bool = False
    returns_source_urls: bool = False
    returns_citations: bool = False
    measures_consumer_ui: bool = False
    notes: str = ""


class VisibilityContext(BaseModel):
    job_id: str
    base_url: str
    brand_tokens: list[str]
    site_registrable_domain: str
    prompt_id: str
    run_index: int
    protocol_version: str = "llm-mention-v1"


class VisibilityObservation(BaseModel):
    provider_name: str
    engine_label: str
    query: str
    prompt_id: str
    run_index: int
    observed_at: datetime
    raw_response: str | None
    raw_storage_permitted: bool = True
    # LLM-text heuristics when retrieval_enabled=false (legacy names kept for back-compat).
    # detected_mention: brand/token mention in model text
    # detected_citation: URL to target domain present in model text (url-mention heuristic)
    detected_mention: bool
    detected_citation: bool
    cited_urls: list[str] = Field(default_factory=list)
    extraction_methodology: str
    provenance: Literal["api_observation", "synthetic_demo", "estimate"]
    meta: dict[str, Any] = Field(default_factory=dict)
    # Schema extensions (A3 / D019)
    model_id: str | None = None
    retrieval_enabled: bool = False
    experiment_kind: ExperimentKind = "llm_mention"
    search_queries: list[str] = Field(default_factory=list)
    source_urls: list[str] = Field(default_factory=list)
    target_domain_appeared: bool | None = None
    target_domain_cited: bool | None = None


@runtime_checkable
class AIVisibilityProvider(Protocol):
    name: str
    capabilities: ProviderCapabilities

    async def run_query(
        self, query: str, *, context: VisibilityContext
    ) -> VisibilityObservation: ...
