"""Perplexity Sonar provider stub (P1-D).

Raises NotImplementedError / skips unless PERPLEXITY_API_KEY is set.
Does NOT fabricate AI search visibility metrics.
"""

from __future__ import annotations

import os

from aeo_mvp.visibility.base import VisibilityContext, VisibilityObservation
from aeo_mvp.visibility.retrieval_base import retrieval_capabilities


class PerplexitySonarProvider:
    """Stub for future Perplexity Sonar / Agent API integration."""

    name = "perplexity_sonar"
    capabilities = retrieval_capabilities(
        "perplexity_sonar",
        returns_search_queries=False,  # Sonar often omits explicit queries
        returns_source_urls=True,
        returns_citations=True,
        notes=(
            "Stub only. Live Sonar/Agent API not implemented in MVP. "
            "When enabled, retrieval_enabled=true and experiment_kind=ai_search_visibility. "
            "Does not measure consumer Perplexity UI."
        ),
    )

    def __init__(self, api_key: str | None = None) -> None:
        self.api_key = api_key if api_key is not None else os.environ.get("PERPLEXITY_API_KEY")

    @property
    def is_configured(self) -> bool:
        return bool(self.api_key)

    async def run_query(
        self, query: str, *, context: VisibilityContext
    ) -> VisibilityObservation:
        if not self.api_key:
            raise NotImplementedError(
                "PerplexitySonarProvider requires PERPLEXITY_API_KEY; "
                "refusing to fabricate AI search visibility metrics."
            )
        raise NotImplementedError(
            "PerplexitySonarProvider live API path is not implemented in this MVP. "
            "Do not use stub output as ai_search_visibility metrics."
        )


def maybe_perplexity_provider() -> PerplexitySonarProvider | None:
    """Return a configured stub provider, or None if no key (skip silently)."""
    key = os.environ.get("PERPLEXITY_API_KEY")
    if not key:
        return None
    return PerplexitySonarProvider(api_key=key)
