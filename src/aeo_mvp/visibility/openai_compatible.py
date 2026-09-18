"""Optional OpenAI-compatible chat completions provider (non-retrieval LLM mention)."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

import httpx

from aeo_mvp.config import get_settings
from aeo_mvp.visibility.base import (
    ProviderCapabilities,
    VisibilityContext,
    VisibilityObservation,
)
from aeo_mvp.visibility.metrics import (
    EXTRACTION_METHODOLOGY,
    detect_citation,
    detect_mention,
    filter_brand_tokens,
)

logger = logging.getLogger(__name__)

# Must not imply browsing / AI search retrieval.
SYSTEM_PROMPT = (
    "You are a research assistant answering factual questions for an offline evaluation "
    "using only your parametric knowledge. "
    "Answer helpfully in 2–4 short paragraphs. If you reference websites from memory, "
    "include full https URLs when you know them. "
    "You cannot browse the web or retrieve live pages in this evaluation."
)

_CAPABILITIES = ProviderCapabilities(
    provider_id="openai_compatible",
    retrieval_enabled=False,
    experiment_kinds=["llm_mention"],
    returns_search_queries=False,
    returns_source_urls=False,
    returns_citations=False,
    measures_consumer_ui=False,
    notes=(
        "OpenAI-compatible /chat/completions without tools. "
        "This is an LLM mention experiment, NOT AI search visibility. "
        "Results are not equivalent to consumer ChatGPT/Gemini/Perplexity UI."
    ),
)


class OpenAICompatibleProvider:
    name = "openai_compatible"
    capabilities = _CAPABILITIES

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str | None = None,
    ) -> None:
        settings = get_settings()
        self.api_key = api_key if api_key is not None else settings.openai_api_key
        self.base_url = (base_url or settings.openai_base_url).rstrip("/")
        self.model = model or settings.openai_model
        if not self.api_key:
            raise ValueError("OPENAI_API_KEY is required for OpenAICompatibleProvider")

    async def run_query(self, query: str, *, context: VisibilityContext) -> VisibilityObservation:
        site_line = f"Site under evaluation: {context.base_url}"
        user_content = f"{query}\n\n{site_line}"
        url = f"{self.base_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_content},
            ],
            "temperature": 0,
        }
        raw = None
        error = False
        meta: dict = {
            "model": self.model,
            "retrieval_enabled": False,
            "experiment_kind": "llm_mention",
            "notes": (
                "LLM mention experiment via chat completions; "
                "NOT AI search visibility / retrieval."
            ),
        }
        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                resp = await client.post(url, headers=headers, json=payload)
                if resp.status_code >= 400:
                    # one retry after 1s for 429/5xx
                    if resp.status_code in (429, 500, 502, 503, 504):
                        await asyncio.sleep(1)
                        resp = await client.post(url, headers=headers, json=payload)
                if resp.status_code >= 400:
                    error = True
                    raw = f"HTTP {resp.status_code}: {resp.text[:2000]}"
                else:
                    data = resp.json()
                    raw = (
                        data.get("choices", [{}])[0]
                        .get("message", {})
                        .get("content")
                    )
                    meta["usage"] = data.get("usage")
        except Exception as exc:  # noqa: BLE001
            logger.warning("openai_compatible error: %s", exc)
            error = True
            raw = str(exc)

        tokens = filter_brand_tokens(context.brand_tokens)
        mention = False
        citation = False
        cited: list[str] = []
        if raw and not error:
            mention = detect_mention(raw, tokens, exclude_suffix=site_line)
            citation, cited = detect_citation(raw, context.site_registrable_domain)
        meta["error"] = error

        return VisibilityObservation(
            provider_name=self.name,
            engine_label=f"openai_compatible:{self.model}",
            query=query,
            prompt_id=context.prompt_id,
            run_index=context.run_index,
            observed_at=datetime.now(timezone.utc),
            raw_response=raw,
            raw_storage_permitted=True,
            detected_mention=mention,
            detected_citation=citation,
            cited_urls=cited,
            extraction_methodology=EXTRACTION_METHODOLOGY,
            provenance="api_observation",
            meta=meta,
            model_id=self.model,
            retrieval_enabled=False,
            experiment_kind="llm_mention",
            search_queries=[],
            source_urls=[],
            target_domain_appeared=None,
            target_domain_cited=None,
        )
