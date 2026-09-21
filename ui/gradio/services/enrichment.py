"""Session-scoped page enrichment cache + selection tokens.

Keyed by ``job_id + page_id`` so revisiting a page is instant and never
crosses Gradio sessions / users. Selection tokens discard stale async
responses when the user navigates quickly (A → B → A finishes late).
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from services.api_client import AeoApiClient, AeoApiError, user_safe_enrichment_error

logger = logging.getLogger(__name__)

# Bound concurrent enrichment calls within a process (Gradio workers share this).
_ENRICH_SEMAPHORE = asyncio.Semaphore(2)

LOADING_MESSAGE = "Additional optimization analysis loading…"


class EnrichmentStatus(str, Enum):
    LOADING = "loading"
    SUCCESS = "success"
    ERROR = "error"
    IDLE = "idle"


@dataclass
class EnrichmentEntry:
    status: EnrichmentStatus
    payload: dict[str, Any] | None = None
    error_message: str | None = None


def cache_key(job_id: str, page_id: str) -> str:
    return f"{job_id}:{page_id}"


@dataclass
class EnrichmentCache:
    """Per-session cache (stored on AnalysisState — not a global)."""

    entries: dict[str, EnrichmentEntry] = field(default_factory=dict)

    def get(self, job_id: str, page_id: str) -> EnrichmentEntry | None:
        return self.entries.get(cache_key(job_id, page_id))

    def set(self, job_id: str, page_id: str, entry: EnrichmentEntry) -> None:
        self.entries[cache_key(job_id, page_id)] = entry

    def clear(self) -> None:
        self.entries.clear()


def next_selection_id(current: int) -> int:
    return int(current or 0) + 1


def is_stale(selection_id: int, expected: int) -> bool:
    return int(selection_id) != int(expected)


async def fetch_content_optimization(
    client: AeoApiClient,
    *,
    job_id: str,
    page_id: str,
    content_draft: bool = True,
) -> EnrichmentEntry:
    """Call the async content-optimization endpoint under a concurrency bound."""
    async with _ENRICH_SEMAPHORE:
        try:
            payload = await client.content_optimization_async(
                job_id=job_id,
                page_id=page_id,
                content_draft=content_draft,
            )
            return EnrichmentEntry(status=EnrichmentStatus.SUCCESS, payload=payload)
        except AeoApiError as exc:
            msg = user_safe_enrichment_error(exc)
            if exc.status_code is None or exc.status_code >= 500:
                logger.exception(
                    "content_optimization failed job=%s page=%s status=%s",
                    job_id,
                    page_id,
                    exc.status_code,
                )
            else:
                logger.warning(
                    "content_optimization user error job=%s page=%s: %s",
                    job_id,
                    page_id,
                    msg,
                )
            return EnrichmentEntry(status=EnrichmentStatus.ERROR, error_message=msg)
        except Exception as exc:  # noqa: BLE001 — never blank the page; always surface safely
            logger.exception("content_optimization unexpected job=%s page=%s", job_id, page_id)
            return EnrichmentEntry(
                status=EnrichmentStatus.ERROR,
                error_message=user_safe_enrichment_error(exc),
            )


def needs_page_enrichment(
    report: dict[str, Any] | None,
    *,
    page_url: str | None,
    page_id: str | None,
) -> bool:
    """True when report page_intelligence does not already cover this page."""
    if not report or not page_url or not page_id:
        return False
    pi = report.get("page_intelligence")
    if not isinstance(pi, dict) or not pi.get("url"):
        # No primary intelligence — still may want per-page opt for secondary pages.
        return True
    return str(pi.get("url")).rstrip("/") != str(page_url).rstrip("/")
