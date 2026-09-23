"""Optional live DigitalOcean test — skipped without key + flag. Not run on cloud VM."""

import pytest

from aeo_mvp.config import get_settings
from aeo_mvp.llm import reset_execution_flags
from aeo_mvp.pipeline import run_pipeline


def _live_enabled() -> bool:
    settings = get_settings()
    return bool(settings.live_retrieval_test and settings.llm_api_key)


@pytest.mark.skipif(
    not _live_enabled(),
    reason="AEO_LIVE_RETRIEVAL_TEST + AEO_LLM_API_KEY required (CoS box only)",
)
def test_live_do_pipeline():
    reset_execution_flags()
    get_settings.cache_clear()
    md = """# Live Probe Article

A short article about DigitalOcean Inference web search for AEO tests.

## What is server-side web search?

Server-side web search lets an inference API fetch sources during a response.

## Why citations matter

Citations show which URLs grounded the answer.

## Agent loops

An agent loop calls tools until the task is finished.
"""
    report = run_pipeline(text=md, target_domain="digitalocean.com", dry_run=False)
    assert report.llm_used is True
    assert report.auto_publish is False
