"""Competitor brand/domain specs for OBSERVED visibility share."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from aeo_mvp.llm import LLMError


@dataclass(frozen=True)
class Competitor:
    """One competitor brand name + optional domain for citation matching."""

    name: str
    domain: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {"name": self.name, "domain": self.domain}


def _normalize_domain(domain: str | None) -> str | None:
    if not domain:
        return None
    d = domain.strip().lower()
    d = re.sub(r"^https?://", "", d)
    d = d.split("/")[0].removeprefix("www.")
    return d or None


def parse_competitor_item(item: Any) -> Competitor:
    if isinstance(item, str):
        # "Name|domain", "Name:domain", or "Name"
        raw = item.strip()
        if not raw:
            raise LLMError("Empty competitor entry")
        if "|" in raw:
            name, _, rest = raw.partition("|")
            domain = rest.strip() or None
        elif ":" in raw and not raw.lower().startswith("http"):
            # Prefer last colon for "Brand Name:domain.com"
            name, _, rest = raw.rpartition(":")
            domain = rest.strip() or None
        else:
            name, domain = raw, None
        name = name.strip()
        if not name:
            raise LLMError(f"Competitor entry missing name: {item!r}")
        return Competitor(name=name, domain=_normalize_domain(domain))

    if isinstance(item, dict):
        name = str(item.get("name") or item.get("brand") or "").strip()
        domain = item.get("domain") or item.get("url") or item.get("site")
        domain_s = str(domain).strip() if domain not in (None, "") else None
        if not name:
            raise LLMError(f"Competitor object missing name: {item!r}")
        return Competitor(name=name, domain=_normalize_domain(domain_s))

    raise LLMError(f"Competitor must be string or object; got {type(item).__name__}")


def parse_competitors(
    raw: str | list[Any] | None = None,
    *,
    competitors_file: str | Path | None = None,
) -> list[Competitor]:
    """Parse competitors from CLI string, JSON file, list, or Gradio textarea.

    CLI / textarea forms (one per line or comma-separated):
      Acme|acme.com
      Beta:beta.io
      Gamma

    JSON file: ``{"competitors":[{"name":"Acme","domain":"acme.com"}]}`` or a list.
    """
    items: list[Any] = []

    if competitors_file:
        p = Path(competitors_file)
        try:
            text = p.read_text(encoding="utf-8")
        except OSError as exc:
            raise LLMError(f"Could not read competitors file {p}: {exc}") from exc
        try:
            payload = json.loads(text)
        except json.JSONDecodeError as exc:
            raise LLMError(f"Invalid competitors JSON {p}: {exc}") from exc
        if isinstance(payload, dict):
            items = list(payload.get("competitors") or payload.get("brands") or [])
        elif isinstance(payload, list):
            items = payload
        else:
            raise LLMError("competitors JSON must be an object or array")

    if isinstance(raw, list):
        items.extend(raw)
    elif isinstance(raw, str) and raw.strip():
        # Split on newlines or commas (but not inside URLs — no http in entries).
        blob = raw.strip()
        if blob.startswith("{") or blob.startswith("["):
            try:
                payload = json.loads(blob)
            except json.JSONDecodeError as exc:
                raise LLMError(f"Invalid competitors JSON paste: {exc}") from exc
            if isinstance(payload, dict):
                items.extend(payload.get("competitors") or payload.get("brands") or [])
            elif isinstance(payload, list):
                items.extend(payload)
            else:
                raise LLMError("competitors JSON must be an object or array")
        else:
            for line in re.split(r"[\n,]+", blob):
                line = line.strip()
                if line and not line.startswith("#"):
                    items.append(line)

    out: list[Competitor] = []
    seen: set[str] = set()
    for item in items:
        c = parse_competitor_item(item)
        key = c.name.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(c)
    return out
