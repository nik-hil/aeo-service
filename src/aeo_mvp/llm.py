"""Thin DigitalOcean Inference client (Responses API).

Uses only AEO_LLM_API_KEY / AEO_LLM_BASE_URL / AEO_LLM_MODEL.
Tracks whether an LLM call and/or web_search tool evidence actually occurred.
Python plumbing only — no semantic judgment.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlparse

import httpx

from aeo_mvp.config import get_settings

logger = logging.getLogger(__name__)

_JSON_FENCE_RE = re.compile(r"```(?:json)?\s*([\s\S]*?)```", re.I)


class LLMError(RuntimeError):
    """Raised when the LLM / Responses call cannot complete honestly."""


@dataclass
class LLMResult:
    text: str
    raw: dict[str, Any] = field(default_factory=dict)
    search_queries: list[str] = field(default_factory=list)
    source_urls: list[str] = field(default_factory=list)
    citations: list[dict[str, Any]] = field(default_factory=list)
    had_web_search_call: bool = False
    llm_called: bool = True
    model: str = ""


_LLM_CALLS = 0
_RETRIEVAL_EVIDENCE = 0


def reset_execution_flags() -> None:
    global _LLM_CALLS, _RETRIEVAL_EVIDENCE
    _LLM_CALLS = 0
    _RETRIEVAL_EVIDENCE = 0


def llm_used() -> bool:
    return _LLM_CALLS > 0


def retrieval_used() -> bool:
    """True only when tool evidence (web_search_call / sources / citations) was seen."""
    return _RETRIEVAL_EVIDENCE > 0


def extract_json(text: str) -> Any:
    """Parse JSON from model text (raw or fenced). Raises LLMError on failure."""
    raw = (text or "").strip()
    if not raw:
        raise LLMError("Empty LLM response; expected JSON")
    candidates = [raw]
    m = _JSON_FENCE_RE.search(raw)
    if m:
        candidates.insert(0, m.group(1).strip())
    # Object/array slice fallback
    for opener, closer in (("{", "}"), ("[", "]")):
        start = raw.find(opener)
        end = raw.rfind(closer)
        if start >= 0 and end > start:
            candidates.append(raw[start : end + 1])
    errors: list[str] = []
    for c in candidates:
        try:
            return json.loads(c)
        except json.JSONDecodeError as exc:
            errors.append(str(exc))
    raise LLMError(f"Could not parse JSON from LLM response: {errors[:2]}")


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def _urls_from_unknown(obj: Any, *, into: list[str]) -> None:
    if isinstance(obj, str):
        if obj.startswith("http://") or obj.startswith("https://"):
            if obj not in into:
                into.append(obj)
        return
    if isinstance(obj, dict):
        for key in ("url", "link", "href", "source_url"):
            val = obj.get(key)
            if isinstance(val, str) and val.startswith("http") and val not in into:
                into.append(val)
        for v in obj.values():
            _urls_from_unknown(v, into=into)
        return
    if isinstance(obj, list):
        for item in obj:
            _urls_from_unknown(item, into=into)


def _collect_queries(web_search_item: dict[str, Any]) -> list[str]:
    action = web_search_item.get("action") or {}
    if not isinstance(action, dict):
        action = {}
    queries: list[str] = []
    for key in ("queries", "query"):
        raw = action.get(key)
        if raw is None and key == "queries":
            raw = web_search_item.get("queries") or web_search_item.get("query")
        for item in _as_list(raw):
            if isinstance(item, str) and item.strip() and item not in queries:
                queries.append(item.strip())
            elif isinstance(item, dict):
                q = item.get("query") or item.get("text") or item.get("q")
                if isinstance(q, str) and q.strip() and q not in queries:
                    queries.append(q.strip())
    return queries


def parse_responses_output(data: dict[str, Any]) -> dict[str, Any]:
    """Extract answer, search queries, source URLs, citations from DO Responses payload."""
    search_queries: list[str] = []
    source_urls: list[str] = []
    citations: list[dict[str, Any]] = []
    answer_parts: list[str] = []
    had_web_search_call = False

    output = data.get("output")
    if not isinstance(output, list):
        nested = data.get("response")
        if isinstance(nested, dict) and isinstance(nested.get("output"), list):
            output = nested["output"]
        else:
            output = []

    for item in output:
        if not isinstance(item, dict):
            continue
        item_type = (item.get("type") or "").lower()
        if item_type in {"web_search_call", "web_search"}:
            had_web_search_call = True
            for q in _collect_queries(item):
                if q not in search_queries:
                    search_queries.append(q)
            action = item.get("action") if isinstance(item.get("action"), dict) else {}
            for key in ("sources", "results", "source_urls"):
                _urls_from_unknown(action.get(key), into=source_urls)
            _urls_from_unknown(item.get("sources"), into=source_urls)
            _urls_from_unknown(item.get("results"), into=source_urls)
            continue

        content = item.get("content")
        if isinstance(content, str) and content.strip():
            answer_parts.append(content.strip())
        elif isinstance(content, list):
            for block in content:
                if not isinstance(block, dict):
                    continue
                text = block.get("text")
                if isinstance(text, str) and text.strip():
                    answer_parts.append(text.strip())
                annotations = block.get("annotations") or block.get("annotation") or []
                for ann in _as_list(annotations):
                    if not isinstance(ann, dict):
                        continue
                    ann_type = (ann.get("type") or "").lower()
                    if ann_type and ann_type not in {"url_citation", "citation"}:
                        continue
                    url = ann.get("url") or ann.get("link")
                    if not isinstance(url, str) or not url.startswith("http"):
                        continue
                    citations.append(
                        {
                            "url": url,
                            "title": ann.get("title"),
                            "type": "url_citation",
                        }
                    )
                    if url not in source_urls:
                        source_urls.append(url)

        if isinstance(item.get("text"), str) and item["text"].strip():
            answer_parts.append(item["text"].strip())

    return {
        "search_queries": search_queries,
        "source_urls": source_urls,
        "citations": citations,
        "answer_text": "\n\n".join(answer_parts).strip(),
        "had_web_search_call": had_web_search_call,
    }


def domain_in_urls(domain: str | None, urls: list[str]) -> bool:
    if not domain:
        return False
    needle = domain.lower().removeprefix("www.")
    for u in urls:
        try:
            host = (urlparse(u).hostname or "").lower().removeprefix("www.")
        except Exception:
            continue
        if host == needle or host.endswith("." + needle):
            return True
    return False


def mention_in_text(text: str, tokens: list[str]) -> bool:
    lower = (text or "").lower()
    for t in tokens:
        if t and t.lower() in lower:
            return True
    return False


class LLMClient:
    """Synchronous client for DigitalOcean Responses API."""

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str | None = None,
        *,
        timeout_s: float | None = None,
    ) -> None:
        settings = get_settings()
        self.api_key = api_key if api_key is not None else settings.llm_api_key
        self.base_url = (base_url or settings.llm_base_url).rstrip("/")
        self.model = model or settings.llm_model
        self.timeout_s = float(timeout_s if timeout_s is not None else settings.llm_timeout_s)
        self.max_uses = max(1, min(5, settings.web_search_max_uses))
        self.max_results = max(1, min(10, settings.web_search_max_results))

    def available(self) -> bool:
        return bool(self.api_key)

    def respond(
        self,
        prompt: str,
        *,
        web_search: bool = False,
        require_web_search: bool = False,
        max_output_tokens: int = 4096,
    ) -> LLMResult:
        global _LLM_CALLS, _RETRIEVAL_EVIDENCE
        if not self.api_key:
            raise LLMError("AEO_LLM_API_KEY is required for LLM calls")

        url = f"{self.base_url}/responses"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload: dict[str, Any] = {
            "model": self.model,
            "input": prompt,
            "max_output_tokens": max(256, min(int(max_output_tokens), 16384)),
            "stream": False,
        }
        if web_search:
            payload["tools"] = [
                {
                    "type": "web_search",
                    "max_uses": self.max_uses,
                    "max_results": self.max_results,
                }
            ]

        try:
            with httpx.Client(timeout=self.timeout_s) as client:
                resp = client.post(url, headers=headers, json=payload)
        except httpx.HTTPError as exc:
            raise LLMError(f"LLM request failed: {exc}") from exc

        if resp.status_code >= 400:
            raise LLMError(
                f"LLM HTTP {resp.status_code}: {(resp.text or '')[:2000]}"
            )

        try:
            data = resp.json()
        except json.JSONDecodeError as exc:
            raise LLMError("LLM returned non-JSON response") from exc

        if not isinstance(data, dict):
            raise LLMError("LLM response JSON was not an object")

        _LLM_CALLS += 1
        parsed = parse_responses_output(data)
        tool_evidence = bool(
            parsed["had_web_search_call"]
            or parsed["search_queries"]
            or parsed["source_urls"]
            or parsed["citations"]
        )
        if tool_evidence:
            _RETRIEVAL_EVIDENCE += 1

        if require_web_search and not tool_evidence:
            raise LLMError(
                "Response did not include web_search tool evidence "
                "(web_search_call / sources / citations). "
                "Refusing to treat as AI search visibility."
            )

        return LLMResult(
            text=parsed["answer_text"] or "",
            raw=data,
            search_queries=list(parsed["search_queries"]),
            source_urls=list(parsed["source_urls"]),
            citations=list(parsed["citations"]),
            had_web_search_call=bool(parsed["had_web_search_call"]),
            llm_called=True,
            model=self.model,
        )

    def respond_json(
        self,
        prompt: str,
        *,
        max_output_tokens: int = 4096,
    ) -> Any:
        result = self.respond(
            prompt,
            web_search=False,
            max_output_tokens=max_output_tokens,
        )
        return extract_json(result.text)
