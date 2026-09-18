"""Retrieval-enabled visibility provider interface (P1-D).

Required observation fields when retrieval_enabled=True:
  - search_queries: queries the model/tool issued (when exposed)
  - source_urls: URLs consulted / returned as sources
  - citations: structured attributions (also mirrored in cited_urls when applicable)
  - target_domain_appeared: whether the target domain appeared in sources/results
  - target_domain_cited: whether the target domain was cited in the answer

Do NOT fake AI search metrics. Stub providers must skip or raise until a real key/API path exists.
Consumer UI measurement is almost always False (see ProviderCapabilities.measures_consumer_ui).
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from aeo_mvp.visibility.base import (
    AIVisibilityProvider,
    ProviderCapabilities,
    VisibilityContext,
    VisibilityObservation,
)

RETRIEVAL_REQUIRED_FIELDS = (
    "search_queries",
    "source_urls",
    "citations",  # may live in meta["citations"] and/or cited_urls
    "target_domain_appeared",
    "target_domain_cited",
)


def retrieval_capabilities(
    provider_id: str,
    *,
    returns_search_queries: bool = True,
    returns_source_urls: bool = True,
    returns_citations: bool = True,
    notes: str = "",
) -> ProviderCapabilities:
    return ProviderCapabilities(
        provider_id=provider_id,
        retrieval_enabled=True,
        experiment_kinds=["ai_search_visibility"],
        returns_search_queries=returns_search_queries,
        returns_source_urls=returns_source_urls,
        returns_citations=returns_citations,
        measures_consumer_ui=False,
        notes=notes
        or (
            "Retrieval-enabled AI search visibility proxy. "
            "Does NOT measure consumer ChatGPT/Gemini/Perplexity UI rankings."
        ),
    )


@runtime_checkable
class RetrievalEnabledVisibilityProvider(AIVisibilityProvider, Protocol):
    """Marker protocol: capabilities.retrieval_enabled must be True."""

    name: str
    capabilities: ProviderCapabilities

    async def run_query(
        self, query: str, *, context: VisibilityContext
    ) -> VisibilityObservation: ...
