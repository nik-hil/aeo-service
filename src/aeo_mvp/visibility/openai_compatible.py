"""Optional OpenAI-compatible chat completions provider (non-retrieval LLM mention).

Fail-closed (P0-4): HTTP/timeout/malformed/config failures raise OpenAICompatibleError
instead of returning a zero-mention VisibilityObservation that looks like SUCCESS.
"""

from __future__ import annotations

import asyncio
import logging
import re
from datetime import datetime, timezone
from typing import Any, Literal

import httpx

from aeo_mvp.config import get_settings
from aeo_mvp.target_site import resolve_target_site_identity
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

ProviderFailureCategory = Literal[
    "missing_credentials",
    "timeout",
    "upstream_http",
    "malformed_response",
    "internal_error",
]

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

_RETRYABLE_STATUS = frozenset({429, 500, 502, 503, 504})
_SECRET_RE = re.compile(
    r"(?i)(authorization\s*[:=]\s*['\"]?Bearer\s+)\S+"
    r"|(Bearer\s+)[A-Za-z0-9._\-+=/]{8,}"
    r"|(api[_-]?key\s*[:=]\s*['\"]?)[^\s'\"]+"
    r"|(sk-[A-Za-z0-9]{10,})"
)


def redact_secrets(text: str) -> str:
    """Strip Authorization / API key material from strings destined for API/logs."""
    if not text:
        return text
    out = _SECRET_RE.sub(
        lambda m: (m.group(1) or m.group(2) or m.group(3) or "") + "[redacted]",
        text,
    )
    return out


class OpenAICompatibleError(RuntimeError):
    """Raised when OpenAI-compatible LLM mention retrieval cannot complete honestly."""

    def __init__(
        self,
        summary: str,
        *,
        category: ProviderFailureCategory,
        status_code: int | None = None,
    ) -> None:
        self.category: ProviderFailureCategory = category
        self.status_code = status_code
        self.provider = "openai_compatible"
        self.operation = "chat.completions"
        safe = redact_secrets(summary)
        self.safe_summary = safe
        super().__init__(self.public_message())

    def public_message(self) -> str:
        """Stable, secret-free message for job.error_message / API responses."""
        base = f"provider-error: openai_compatible/{self.category}: {self.safe_summary}"
        if self.status_code is not None and "HTTP" not in self.safe_summary:
            return f"{base} (HTTP {self.status_code})"
        return base


def _log_provider_failure(
    *,
    category: ProviderFailureCategory,
    summary: str,
    job_id: str | None = None,
    status_code: int | None = None,
) -> None:
    logger.warning(
        "provider_failure provider=%s operation=%s category=%s job_id=%s "
        "status_code=%s summary=%s",
        "openai_compatible",
        "chat.completions",
        category,
        job_id or "-",
        status_code if status_code is not None else "-",
        redact_secrets(summary),
    )


def _extract_message_content(data: Any) -> str:
    """Parse chat.completions JSON; raise malformed_response on invalid shape."""
    if not isinstance(data, dict):
        raise OpenAICompatibleError(
            "response JSON root is not an object",
            category="malformed_response",
        )
    choices = data.get("choices")
    if not isinstance(choices, list) or not choices:
        raise OpenAICompatibleError(
            "response missing non-empty choices[]",
            category="malformed_response",
        )
    first = choices[0]
    if not isinstance(first, dict):
        raise OpenAICompatibleError(
            "choices[0] is not an object",
            category="malformed_response",
        )
    message = first.get("message")
    if not isinstance(message, dict):
        raise OpenAICompatibleError(
            "choices[0].message missing or invalid",
            category="malformed_response",
        )
    content = message.get("content")
    if content is None:
        raise OpenAICompatibleError(
            "choices[0].message.content is null",
            category="malformed_response",
        )
    if not isinstance(content, str):
        raise OpenAICompatibleError(
            "choices[0].message.content is not a string",
            category="malformed_response",
        )
    return content


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
            raise OpenAICompatibleError(
                "OPENAI_API_KEY is required for OpenAICompatibleProvider",
                category="missing_credentials",
            )

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
        meta: dict = {
            "model": self.model,
            "retrieval_enabled": False,
            "experiment_kind": "llm_mention",
            "notes": (
                "LLM mention experiment via chat completions; "
                "NOT AI search visibility / retrieval."
            ),
        }
        job_id = getattr(context, "job_id", None)

        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                resp = await client.post(url, headers=headers, json=payload)
                if resp.status_code >= 400 and resp.status_code in _RETRYABLE_STATUS:
                    # One retry after 1s for 429/5xx only (preserve existing policy).
                    await asyncio.sleep(1)
                    resp = await client.post(url, headers=headers, json=payload)
                if resp.status_code >= 400:
                    summary = f"upstream HTTP {resp.status_code}"
                    _log_provider_failure(
                        category="upstream_http",
                        summary=summary,
                        job_id=job_id,
                        status_code=resp.status_code,
                    )
                    raise OpenAICompatibleError(
                        summary,
                        category="upstream_http",
                        status_code=resp.status_code,
                    )
                try:
                    data = resp.json()
                except ValueError as exc:
                    _log_provider_failure(
                        category="malformed_response",
                        summary="response body is not valid JSON",
                        job_id=job_id,
                        status_code=resp.status_code,
                    )
                    raise OpenAICompatibleError(
                        "response body is not valid JSON",
                        category="malformed_response",
                        status_code=resp.status_code,
                    ) from exc
                try:
                    raw = _extract_message_content(data)
                except OpenAICompatibleError as exc:
                    _log_provider_failure(
                        category=exc.category,
                        summary=exc.safe_summary,
                        job_id=job_id,
                        status_code=resp.status_code,
                    )
                    raise
                meta["usage"] = data.get("usage") if isinstance(data, dict) else None
        except OpenAICompatibleError:
            raise
        except httpx.TimeoutException as exc:
            _log_provider_failure(
                category="timeout",
                summary="request timed out",
                job_id=job_id,
            )
            raise OpenAICompatibleError(
                "request timed out",
                category="timeout",
            ) from exc
        except httpx.HTTPError as exc:
            summary = f"transport error: {type(exc).__name__}"
            _log_provider_failure(
                category="upstream_http",
                summary=summary,
                job_id=job_id,
            )
            raise OpenAICompatibleError(
                summary,
                category="upstream_http",
            ) from exc
        except Exception as exc:  # noqa: BLE001 — map then re-raise typed error
            summary = f"internal provider exception: {type(exc).__name__}"
            _log_provider_failure(
                category="internal_error",
                summary=summary,
                job_id=job_id,
            )
            raise OpenAICompatibleError(
                summary,
                category="internal_error",
            ) from exc

        tokens = filter_brand_tokens(context.brand_tokens)
        mention = detect_mention(raw, tokens, exclude_suffix=site_line)
        # Same TargetSiteIdentity / target_match as AI-search DO path (P1-12).
        # Never match LLM URL mentions via bare site_registrable_domain PSL alone.
        identity = resolve_target_site_identity(
            context.base_url,
            scope=(
                context.target_domain_scope  # type: ignore[arg-type]
                if context.target_domain_scope
                in {"registrable_domain", "hostname", "origin"}
                else None
            ),
        )
        citation, cited = detect_citation(raw, identity)

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
