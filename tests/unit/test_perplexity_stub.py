"""Perplexity stub must not fabricate AI search metrics."""

from __future__ import annotations

import pytest

from aeo_mvp.visibility.base import VisibilityContext
from aeo_mvp.visibility.perplexity_sonar import PerplexitySonarProvider
from aeo_mvp.visibility.retrieval_base import RETRIEVAL_REQUIRED_FIELDS


@pytest.mark.asyncio
async def test_perplexity_raises_without_key():
    p = PerplexitySonarProvider(api_key=None)
    assert p.capabilities.retrieval_enabled is True
    assert "ai_search_visibility" in p.capabilities.experiment_kinds
    ctx = VisibilityContext(
        job_id="j",
        base_url="https://demo.example/",
        brand_tokens=["AcmeFlow"],
        site_registrable_domain="demo.example",
        prompt_id="q1",
        run_index=0,
    )
    with pytest.raises(NotImplementedError):
        await p.run_query("What is AcmeFlow?", context=ctx)


def test_retrieval_required_fields_documented():
    assert "search_queries" in RETRIEVAL_REQUIRED_FIELDS
    assert "target_domain_cited" in RETRIEVAL_REQUIRED_FIELDS
