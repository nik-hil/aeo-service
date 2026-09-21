"""Thin HTTP client for the secured AEO API. No business logic."""

from __future__ import annotations

import os
import time
from dataclasses import dataclass
from typing import Any

import httpx


class AeoApiError(Exception):
    def __init__(self, message: str, *, status_code: int | None = None, body: Any = None):
        super().__init__(message)
        self.status_code = status_code
        self.body = body


@dataclass
class JobRef:
    id: str
    status: str
    base_url: str
    demo_mode: bool


class AeoApiClient:
    def __init__(
        self,
        base_url: str | None = None,
        api_key: str | None = None,
        *,
        timeout: float = 60.0,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.base_url = (base_url or os.environ.get("AEO_API_BASE_URL") or "http://127.0.0.1:8000").rstrip(
            "/"
        )
        self.api_key = api_key if api_key is not None else os.environ.get("AEO_API_KEY", "")
        self.timeout = timeout
        self._transport = transport

    def _headers(self) -> dict[str, str]:
        headers = {"Accept": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    def _client(self) -> httpx.Client:
        return httpx.Client(
            base_url=self.base_url,
            headers=self._headers(),
            timeout=self.timeout,
            transport=self._transport,
        )

    def _raise_for_status(self, resp: httpx.Response) -> None:
        if resp.is_success:
            return
        detail: Any
        try:
            payload = resp.json()
            detail = payload.get("detail", payload)
        except Exception:  # noqa: BLE001
            detail = resp.text
        if isinstance(detail, list):
            message = "; ".join(str(x) for x in detail)
        else:
            message = str(detail)
        raise AeoApiError(message, status_code=resp.status_code, body=detail)

    def health(self) -> dict[str, Any]:
        with self._client() as client:
            resp = client.get("/health")
            self._raise_for_status(resp)
            return resp.json()

    def create_job(
        self,
        url: str,
        *,
        demo_mode: bool = False,
        options: dict[str, Any] | None = None,
    ) -> JobRef:
        payload = {"url": url, "demo_mode": demo_mode, "options": options or {}}
        with self._client() as client:
            resp = client.post("/api/v1/jobs", json=payload)
            self._raise_for_status(resp)
            data = resp.json()
        return JobRef(
            id=data["id"],
            status=data.get("status", "pending"),
            base_url=data.get("base_url", url),
            demo_mode=bool(data.get("demo_mode")),
        )

    def get_job(self, job_id: str) -> dict[str, Any]:
        with self._client() as client:
            resp = client.get(f"/api/v1/jobs/{job_id}")
            self._raise_for_status(resp)
            return resp.json()

    def get_report(self, job_id: str) -> dict[str, Any]:
        with self._client() as client:
            resp = client.get(f"/api/v1/jobs/{job_id}/report")
            self._raise_for_status(resp)
            return resp.json()

    def get_pages(self, job_id: str) -> dict[str, Any]:
        with self._client() as client:
            resp = client.get(f"/api/v1/jobs/{job_id}/pages")
            self._raise_for_status(resp)
            return resp.json()

    def content_optimization(
        self,
        *,
        job_id: str,
        page_id: str | None = None,
        content_draft: bool = False,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "job_id": job_id,
            "content_optimization": True,
            "content_draft": content_draft,
        }
        if page_id:
            payload["page_id"] = page_id
        with self._client() as client:
            resp = client.post("/api/v1/content-optimization", json=payload)
            self._raise_for_status(resp)
            return resp.json()

    def wait_for_job(
        self,
        job_id: str,
        *,
        poll_interval: float = 0.5,
        timeout: float = 180.0,
        on_status: Any | None = None,
    ) -> dict[str, Any]:
        deadline = time.monotonic() + timeout
        last: dict[str, Any] = {}
        while time.monotonic() < deadline:
            last = self.get_job(job_id)
            status = last.get("status")
            if on_status:
                on_status(status, last)
            if status in {"completed", "failed"}:
                return last
            time.sleep(poll_interval)
        raise AeoApiError(
            f"Timed out waiting for job {job_id} (last status={last.get('status')})",
            status_code=None,
            body=last,
        )
