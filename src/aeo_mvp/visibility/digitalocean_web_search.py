"""DigitalOcean Inference Responses API + web_search (AI search visibility).

Official docs:
  https://docs.digitalocean.com/products/inference/how-to/use-server-side-tools/use-web-search/
  https://docs.digitalocean.com/products/inference/how-to/use-responses-api/

Auth env: DO_MODEL_ACCESS_KEY (preferred) or MODEL_ACCESS_KEY (DO docs name).

Never fabricates results. Missing key / HTTP errors / missing web_search raise explicitly.
Does NOT measure consumer ChatGPT/Gemini/Perplexity UI (measures_consumer_ui=false).
"""

from __future__ import annotations

import copy
import json
import logging
import os
from datetime import datetime, timezone
from typing import Any

import httpx

from aeo_mvp.config import get_settings
from aeo_mvp.target_site import (
    MATCH_RULE_VERSION,
    build_target_site_match_audit,
    resolve_target_site_identity,
    target_match,
)
from aeo_mvp.visibility.base import VisibilityContext, VisibilityObservation
from aeo_mvp.visibility.metrics import (
    AI_SEARCH_EXTRACTION_METHODOLOGY,
    detect_mention,
    filter_brand_tokens,
)
from aeo_mvp.visibility.retrieval_base import retrieval_capabilities

logger = logging.getLogger(__name__)

EXTRACTION_METHODOLOGY = AI_SEARCH_EXTRACTION_METHODOLOGY
# Tagged in observation meta as match_rule_version=domain-match-v1 (D023).


class DigitalOceanWebSearchError(RuntimeError):
    """Raised when DigitalOcean web_search retrieval cannot be completed honestly."""


def _resolve_api_key(explicit: str | None = None) -> str | None:
    if explicit:
        return explicit
    settings = get_settings()
    return (
        settings.do_model_access_key
        or settings.model_access_key
        or os.environ.get("DO_MODEL_ACCESS_KEY")
        or os.environ.get("MODEL_ACCESS_KEY")
    )


def _clamp_int(value: int, lo: int, hi: int) -> int:
    return max(lo, min(hi, int(value)))


def _sanitize_for_storage(payload: Any) -> Any:
    """Deep-copy JSON-like data and strip secrets / auth material."""
    if isinstance(payload, dict):
        out: dict[str, Any] = {}
        for k, v in payload.items():
            key_l = str(k).lower()
            if key_l in {"authorization", "api_key", "access_key", "token", "bearer"}:
                out[k] = "[redacted]"
                continue
            if isinstance(v, str) and key_l.endswith("key") and len(v) > 8:
                out[k] = "[redacted]"
                continue
            out[k] = _sanitize_for_storage(v)
        return out
    if isinstance(payload, list):
        return [_sanitize_for_storage(x) for x in payload]
    return payload


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


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


def _parse_responses_output(data: dict[str, Any]) -> dict[str, Any]:
    """Extract search_queries, source_urls, citations, answer text from DO Responses payload."""
    search_queries: list[str] = []
    source_urls: list[str] = []
    citations: list[dict[str, Any]] = []
    answer_parts: list[str] = []

    output = data.get("output")
    if not isinstance(output, list):
        # Some gateways nest under response.output
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
            for q in _collect_queries(item):
                if q not in search_queries:
                    search_queries.append(q)
            action = item.get("action") if isinstance(item.get("action"), dict) else {}
            for key in ("sources", "results", "source_urls"):
                _urls_from_unknown(action.get(key), into=source_urls)
            _urls_from_unknown(item.get("sources"), into=source_urls)
            _urls_from_unknown(item.get("results"), into=source_urls)
            continue

        # message / output_text content
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
                    citation = {
                        "url": url,
                        "title": ann.get("title"),
                        "start_index": ann.get("start_index", ann.get("startIndex")),
                        "end_index": ann.get("end_index", ann.get("endIndex")),
                        "type": "url_citation",
                    }
                    citations.append(citation)
                    if url not in source_urls:
                        source_urls.append(url)

        # top-level text on message items
        if isinstance(item.get("text"), str) and item["text"].strip():
            answer_parts.append(item["text"].strip())

    answer_text = "\n\n".join(answer_parts).strip() or None
    return {
        "search_queries": search_queries,
        "source_urls": source_urls,
        "citations": citations,
        "answer_text": answer_text,
    }


class DigitalOceanWebSearchProvider:
    """Retrieval-enabled AI search visibility via DigitalOcean Inference web_search."""

    name = "digitalocean_web_search"
    capabilities = retrieval_capabilities(
        "digitalocean_web_search",
        returns_search_queries=True,
        returns_source_urls=True,
        returns_citations=True,
        notes=(
            "DigitalOcean Inference Responses API with web_search tool (Exa-backed). "
            "API observation only — does NOT measure consumer ChatGPT/Gemini/Perplexity UI. "
            "measures_consumer_ui=false. Provenance=api_observation."
        ),
    )

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str | None = None,
        *,
        max_uses: int | None = None,
        max_results: int | None = None,
        timeout_s: float | None = None,
    ) -> None:
        settings = get_settings()
        self.api_key = _resolve_api_key(api_key)
        if not self.api_key:
            raise DigitalOceanWebSearchError(
                "DigitalOceanWebSearchProvider requires DO_MODEL_ACCESS_KEY "
                "(or MODEL_ACCESS_KEY). Refusing to fabricate AI search visibility results."
            )
        self.base_url = (base_url or settings.do_inference_base_url).rstrip("/")
        self.model = model or settings.do_inference_model
        self.max_uses = _clamp_int(
            max_uses if max_uses is not None else settings.do_web_search_max_uses,
            1,
            5,
        )
        self.max_results = _clamp_int(
            max_results if max_results is not None else settings.do_web_search_max_results,
            1,
            10,
        )
        self.timeout_s = float(
            timeout_s if timeout_s is not None else settings.do_inference_timeout_s
        )

    async def run_query(
        self, query: str, *, context: VisibilityContext
    ) -> VisibilityObservation:
        if not self.api_key:
            raise DigitalOceanWebSearchError(
                "DO_MODEL_ACCESS_KEY missing; cannot run web_search retrieval."
            )

        url = f"{self.base_url}/responses"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        site_line = f"Site under evaluation: {context.base_url}"
        user_input = (
            f"{query}\n\n{site_line}\n"
            "When you search the web, prefer authoritative sources. "
            "Cite sources with URLs when available."
        )
        payload = {
            "model": self.model,
            "input": user_input,
            "tools": [
                {
                    "type": "web_search",
                    "max_uses": self.max_uses,
                    "max_results": self.max_results,
                }
            ],
            "max_output_tokens": 1024,
            "stream": False,
        }

        try:
            async with httpx.AsyncClient(timeout=self.timeout_s) as client:
                resp = await client.post(url, headers=headers, json=payload)
        except httpx.HTTPError as exc:
            logger.warning("digitalocean_web_search transport error: %s", exc)
            raise DigitalOceanWebSearchError(
                f"DigitalOcean Inference request failed: {exc}"
            ) from exc

        if resp.status_code >= 400:
            body_preview = (resp.text or "")[:2000]
            raise DigitalOceanWebSearchError(
                f"DigitalOcean Inference HTTP {resp.status_code}: {body_preview}"
            )

        try:
            data = resp.json()
        except json.JSONDecodeError as exc:
            raise DigitalOceanWebSearchError(
                "DigitalOcean Inference returned non-JSON response"
            ) from exc

        if not isinstance(data, dict):
            raise DigitalOceanWebSearchError(
                "DigitalOcean Inference response JSON was not an object"
            )

        parsed = _parse_responses_output(data)
        # Require evidence that web_search ran (call item and/or queries/sources/citations).
        output = data.get("output") if isinstance(data.get("output"), list) else []
        has_web_search_call = any(
            isinstance(it, dict)
            and (it.get("type") or "").lower() in {"web_search_call", "web_search"}
            for it in output
        )
        if not (
            has_web_search_call
            or parsed["search_queries"]
            or parsed["source_urls"]
            or parsed["citations"]
        ):
            raise DigitalOceanWebSearchError(
                "DigitalOcean response did not include web_search tool output "
                "(web_search_call / sources / citations). "
                "Refusing to treat as AI search visibility."
            )

        # Target site identity (domain-match-v1) — not bare PSL equality.
        identity = resolve_target_site_identity(
            context.base_url,
            scope=(
                context.target_domain_scope  # type: ignore[arg-type]
                if context.target_domain_scope
                in {"registrable_domain", "hostname", "origin"}
                else None
            ),
        )

        citations = parsed["citations"]
        source_urls = list(parsed["source_urls"])
        citation_urls = [
            c["url"]
            for c in citations
            if isinstance(c.get("url"), str)
        ]
        cited_target_urls = [u for u in citation_urls if target_match(u, identity)]
        matched_sources = [u for u in source_urls if target_match(u, identity)]
        target_domain_cited = len(cited_target_urls) > 0
        # Appearance from sources; structured citations also count as appearance.
        target_domain_appeared = len(matched_sources) > 0 or target_domain_cited

        answer = parsed["answer_text"] or ""
        tokens = filter_brand_tokens(context.brand_tokens)
        mention = detect_mention(answer, tokens, exclude_suffix=site_line) if answer else False

        sanitized = _sanitize_for_storage(copy.deepcopy(data))
        # Never persist the request Authorization header; raw is response body only.
        raw_response = json.dumps(sanitized, sort_keys=True)[:50000]

        match_audit = build_target_site_match_audit(
            identity=identity,
            source_urls=source_urls,
            citation_urls=citation_urls,
        )
        # Align appeared/cited flags with provider OR semantics for citations.
        match_audit["appeared"] = target_domain_appeared
        match_audit["cited"] = target_domain_cited
        if target_domain_cited and not match_audit["matched_urls_appeared"]:
            # Citations counted as appearance — reflect in audit lists.
            match_audit["matched_urls_appeared"] = list(
                match_audit["matched_urls_cited"]
            )
            match_audit["matched_source_urls"] = list(
                match_audit["matched_citation_urls"]
            )

        meta: dict[str, Any] = {
            "model": self.model,
            "retrieval_enabled": True,
            "experiment_kind": "ai_search_visibility",
            "protocol_version": "ai-search-vis-v1",
            "provider": self.name,
            "citations": citations,
            "web_search": {
                "max_uses": self.max_uses,
                "max_results": self.max_results,
                "had_web_search_call": has_web_search_call,
            },
            "notes": (
                "API observation via DigitalOcean Inference web_search. "
                "Not consumer ChatGPT/Gemini/Perplexity UI. measures_consumer_ui=false."
            ),
            "answer_text": answer[:8000] if answer else None,
            "match_rule_version": MATCH_RULE_VERSION,
            "target_site": identity.to_audit_dict(),
            "target_site_match": match_audit,
        }

        return VisibilityObservation(
            provider_name=self.name,
            engine_label=f"digitalocean_web_search:{self.model}",
            query=query,
            prompt_id=context.prompt_id,
            run_index=context.run_index,
            observed_at=datetime.now(timezone.utc),
            raw_response=raw_response,
            raw_storage_permitted=True,
            detected_mention=mention,
            # For retrieval experiments, detected_citation mirrors structured citations only.
            detected_citation=target_domain_cited,
            cited_urls=cited_target_urls,
            extraction_methodology=EXTRACTION_METHODOLOGY,
            provenance="api_observation",
            meta=meta,
            model_id=self.model,
            retrieval_enabled=True,
            experiment_kind="ai_search_visibility",
            search_queries=parsed["search_queries"],
            source_urls=source_urls,
            target_domain_appeared=target_domain_appeared,
            target_domain_cited=target_domain_cited,
        )

