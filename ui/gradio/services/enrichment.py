"""Session-scoped page enrichment cache + selection tokens.

Keyed by ``job_id + page_id`` so revisiting a page is instant and never
crosses Gradio sessions / users. Selection tokens discard stale async
responses when the user navigates quickly (A → B → A finishes late).

In-flight dedupe is also session-scoped: a ``LOADING`` entry on this cache
means a fetch is already running for that key. Callers wait instead of
posting again. ``_CACHE_LOCK`` only serializes those updates. It does not
store payloads or share them across sessions.
"""

from __future__ import annotations

import asyncio
import logging
import threading
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from services.api_client import AeoApiClient, AeoApiError, user_safe_enrichment_error

logger = logging.getLogger(__name__)

# Bound concurrent enrichment calls within a process (Gradio workers share this).
_ENRICH_SEMAPHORE = asyncio.Semaphore(2)

LOADING_MESSAGE = "Additional optimization analysis loading…"
# Client HTTP timeout is 60s. Wait a bit longer so the owner can store SUCCESS/ERROR.
INFLIGHT_WAIT_SECONDS = 90.0
# Mutex only. Enrichment payloads stay on the session EnrichmentCache.
_CACHE_LOCK = threading.RLock()


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
    owner_token: int | None = None


def cache_key(job_id: str, page_id: str) -> str:
    return f"{job_id}:{page_id}"


@dataclass
class EnrichmentCache:
    """Per-session cache (stored on AnalysisState — not a global)."""

    entries: dict[str, EnrichmentEntry] = field(default_factory=dict)
    _ticket: int = 0

    def get(self, job_id: str, page_id: str) -> EnrichmentEntry | None:
        with _CACHE_LOCK:
            return self.entries.get(cache_key(job_id, page_id))

    def set(self, job_id: str, page_id: str, entry: EnrichmentEntry) -> None:
        with _CACHE_LOCK:
            self.entries[cache_key(job_id, page_id)] = entry

    def clear(self) -> None:
        with _CACHE_LOCK:
            self.entries.clear()

    def claim(self, job_id: str, page_id: str) -> tuple[str, int | None]:
        """Atomically reserve a fetch or observe an existing entry.

        Returns ``(role, owner_token)``.

        - ``owner``: this caller must fetch. Entry is LOADING with ``owner_token``.
        - ``in_flight``: LOADING already — do not POST. Token is None.
        - ``settled``: SUCCESS or ERROR already cached — do not POST.
        """
        with _CACHE_LOCK:
            key = cache_key(job_id, page_id)
            existing = self.entries.get(key)
            if existing and existing.status in (
                EnrichmentStatus.SUCCESS,
                EnrichmentStatus.ERROR,
            ):
                return "settled", None
            if existing and existing.status == EnrichmentStatus.LOADING:
                return "in_flight", None
            self._ticket += 1
            token = self._ticket
            self.entries[key] = EnrichmentEntry(
                status=EnrichmentStatus.LOADING, owner_token=token
            )
            return "owner", token

    def pop_if_loading(self, job_id: str, page_id: str, token: int | None) -> bool:
        """Drop this owner's LOADING marker. Never removes SUCCESS, ERROR, or another owner."""
        if token is None:
            return False
        with _CACHE_LOCK:
            key = cache_key(job_id, page_id)
            existing = self.entries.get(key)
            if (
                existing is not None
                and existing.status == EnrichmentStatus.LOADING
                and existing.owner_token == token
            ):
                self.entries.pop(key, None)
                return True
            return False


def next_selection_id(current: int) -> int:
    return int(current or 0) + 1


def is_stale(selection_id: int, expected: int) -> bool:
    return int(selection_id) != int(expected)


async def wait_for_terminal(
    cache: EnrichmentCache,
    job_id: str,
    page_id: str,
    *,
    timeout: float = INFLIGHT_WAIT_SECONDS,
    poll: float = 0.05,
) -> EnrichmentEntry | None:
    """Wait until ``LOADING`` is replaced or removed. Does not clear the owner's entry.

    Returns the terminal entry, ``None`` if the owner dropped LOADING, or the
    still-LOADING entry if ``timeout`` elapses.
    """
    deadline = time.monotonic() + timeout
    while True:
        entry = cache.get(job_id, page_id)
        if entry is None or entry.status != EnrichmentStatus.LOADING:
            return entry
        if time.monotonic() >= deadline:
            return entry
        await asyncio.sleep(poll)


def wait_for_terminal_sync(
    cache: EnrichmentCache,
    job_id: str,
    page_id: str,
    *,
    timeout: float = INFLIGHT_WAIT_SECONDS,
    poll: float = 0.05,
) -> EnrichmentEntry | None:
    """Sync twin of ``wait_for_terminal`` for the Analyze worker thread."""
    deadline = time.monotonic() + timeout
    while True:
        entry = cache.get(job_id, page_id)
        if entry is None or entry.status != EnrichmentStatus.LOADING:
            return entry
        if time.monotonic() >= deadline:
            return entry
        time.sleep(poll)


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
