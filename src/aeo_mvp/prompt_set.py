"""Frozen prompt-set loader (versioned JSON).

When a prompt set is provided, visibility uses these prompts **instead of**
LLM query rediscovery. Format is documented in ``docs/PROMPT_SET.md``.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from aeo_mvp.llm import LLMError
from aeo_mvp.queries import Query, QuerySet

PromptKind = Literal["general", "branded", "factual"]

_VALID_KINDS = frozenset({"general", "branded", "factual"})
MIN_FROZEN = 1
MAX_FROZEN = 50
MIN_Q_LEN = 8
MAX_Q_LEN = 400


@dataclass
class FrozenPrompt:
    text: str
    kind: PromptKind = "general"
    id: str | None = None


@dataclass
class PromptSet:
    """Versioned list of prompts used instead of LLM rediscovery."""

    version: str
    prompts: list[FrozenPrompt] = field(default_factory=list)
    source_path: str | None = None
    notes: str = ""

    def to_queryset(self) -> QuerySet:
        selected = [
            Query(
                text=p.text,
                importance="medium",
                reason=f"frozen prompt set v{self.version}"
                + (f" ({p.kind})" if p.kind != "general" else ""),
                article_topics_or_evidence=p.kind,
                source="frozen_prompt_set",
                kind=p.kind,
                prompt_id=p.id,
            )
            for p in self.prompts
        ]
        return QuerySet(
            candidates=list(selected),
            selected=selected,
            quality_notes=(
                self.notes
                or f"Frozen prompt set v{self.version} "
                f"({len(selected)} prompts; LLM rediscovery skipped)."
            ),
            model="",
        )


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip())


def _parse_kind(raw: Any) -> PromptKind:
    k = str(raw or "general").strip().lower()
    if k not in _VALID_KINDS:
        raise LLMError(
            f"Invalid prompt kind {raw!r}; expected one of {sorted(_VALID_KINDS)}"
        )
    return k  # type: ignore[return-value]


def _prompt_from_item(item: Any, index: int) -> FrozenPrompt:
    if isinstance(item, str):
        text = _normalize(item)
        kind: PromptKind = "general"
        pid = None
    elif isinstance(item, dict):
        text = _normalize(str(item.get("text") or item.get("prompt") or item.get("question") or ""))
        kind = _parse_kind(item.get("kind") or item.get("type") or "general")
        raw_id = item.get("id")
        pid = str(raw_id).strip() if raw_id not in (None, "") else None
    else:
        raise LLMError(f"Prompt item #{index} must be a string or object")

    if not text or len(text) < MIN_Q_LEN or len(text) > MAX_Q_LEN:
        raise LLMError(
            f"Prompt item #{index} text must be {MIN_Q_LEN}–{MAX_Q_LEN} characters "
            f"after normalize; got {len(text)}"
        )
    return FrozenPrompt(text=text, kind=kind, id=pid or f"p{index}")


def parse_prompt_set_payload(raw: Any, *, source_path: str | None = None) -> PromptSet:
    """Parse a JSON object or list into a PromptSet."""
    if isinstance(raw, list):
        version = "1"
        items = raw
        notes = ""
    elif isinstance(raw, dict):
        version = str(raw.get("version") or "1").strip() or "1"
        items = raw.get("prompts") or raw.get("questions") or raw.get("items") or []
        notes = str(raw.get("notes") or "").strip()
        if not isinstance(items, list):
            raise LLMError("prompt set JSON: prompts must be an array")
    else:
        raise LLMError("prompt set JSON must be an object or array")

    if not items:
        raise LLMError("prompt set has no prompts")

    prompts: list[FrozenPrompt] = []
    seen: set[str] = set()
    for i, item in enumerate(items, start=1):
        p = _prompt_from_item(item, i)
        key = re.sub(r"[^\w\s]", "", p.text.lower()).strip()
        if key in seen:
            continue
        seen.add(key)
        prompts.append(p)

    if len(prompts) < MIN_FROZEN:
        raise LLMError(f"Need at least {MIN_FROZEN} prompt after validation")
    if len(prompts) > MAX_FROZEN:
        prompts = prompts[:MAX_FROZEN]

    return PromptSet(
        version=version,
        prompts=prompts,
        source_path=source_path,
        notes=notes,
    )


def load_prompt_set_json(path: str | Path) -> PromptSet:
    """Load a versioned prompt set from a JSON file."""
    p = Path(path)
    try:
        text = p.read_text(encoding="utf-8")
    except OSError as exc:
        raise LLMError(f"Could not read prompts file {p}: {exc}") from exc
    try:
        raw = json.loads(text)
    except json.JSONDecodeError as exc:
        raise LLMError(f"Invalid JSON in prompts file {p}: {exc}") from exc
    return parse_prompt_set_payload(raw, source_path=str(p))


def parse_prompts_text(text: str) -> PromptSet:
    """Parse pasted prompts: JSON object/array, or one prompt per non-empty line.

    Lines starting with ``#`` are ignored in line mode. Optional prefix
    ``branded:`` / ``factual:`` / ``general:`` sets kind.
    """
    raw = (text or "").strip()
    if not raw:
        raise LLMError("Empty prompts paste")

    if raw.startswith("{") or raw.startswith("["):
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise LLMError(f"Invalid prompts JSON paste: {exc}") from exc
        return parse_prompt_set_payload(payload, source_path="<paste>")

    items: list[dict[str, str]] = []
    for line in raw.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        kind = "general"
        body = line
        for prefix in ("branded:", "factual:", "general:"):
            if line.lower().startswith(prefix):
                kind = prefix[:-1]
                body = line[len(prefix) :].strip()
                break
        items.append({"text": body, "kind": kind})
    return parse_prompt_set_payload(
        {"version": "1", "prompts": items, "notes": "pasted line prompts"},
        source_path="<paste>",
    )


def resolve_prompt_set(
    *,
    prompts_file: str | Path | None = None,
    prompts_text: str | None = None,
) -> PromptSet | None:
    """Return a PromptSet when file and/or paste provided; else None.

    File wins when both are set (paste ignored).
    """
    if prompts_file:
        return load_prompt_set_json(prompts_file)
    paste = (prompts_text or "").strip()
    if paste:
        return parse_prompts_text(paste)
    return None
