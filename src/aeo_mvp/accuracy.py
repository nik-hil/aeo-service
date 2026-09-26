"""Brand-fact / accuracy pass: OBSERVED answer claims vs CURRENT.md.

LLM compares only the DigitalOcean web_search answer text against the article.
No invented world fact-check beyond those two sources.
Labels: OBSERVED (answer) vs LLM-GENERATED (conflict flags).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Protocol

from aeo_mvp.article import Article
from aeo_mvp.llm import LLMClient, LLMError
from aeo_mvp.queries import Query, QuerySet
from aeo_mvp.visibility import VisibilityReport

_ACCURACY_KINDS = frozenset({"branded", "factual"})


class SupportsRespondJSON(Protocol):
    def respond_json(self, prompt: str, *, max_output_tokens: int = 4096) -> Any: ...

    @property
    def model(self) -> str: ...


@dataclass
class AccuracyConflict:
    query: str
    claim_from_observed_answer: str
    evidence_quote_from_current: str
    note: str = ""
    severity: str = "medium"  # low | medium | high
    provenance: str = "llm_generated"

    def to_dict(self) -> dict[str, Any]:
        return {
            "query": self.query,
            "claim_from_observed_answer": self.claim_from_observed_answer,
            "evidence_quote_from_current": self.evidence_quote_from_current,
            "note": self.note,
            "severity": self.severity,
            "provenance": self.provenance,
            "label": "LLM-GENERATED",
        }


@dataclass
class AccuracyCheck:
    query: str
    kind: str
    skipped: bool = False
    skip_reason: str = ""
    conflict_count: int = 0
    observed_answer_preview: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "query": self.query,
            "kind": self.kind,
            "skipped": self.skipped,
            "skip_reason": self.skip_reason,
            "conflict_count": self.conflict_count,
            "observed_answer_preview": self.observed_answer_preview[:400],
            "observed_label": "OBSERVED",
        }


@dataclass
class AccuracyReport:
    checks: list[AccuracyCheck] = field(default_factory=list)
    conflicts: list[AccuracyConflict] = field(default_factory=list)
    model: str = ""
    notes: str = (
        "LLM-GENERATED conflict flags: compare OBSERVED DigitalOcean web_search "
        "answer claims against CURRENT.md only. Not a world fact-check. "
        "Does not measure ChatGPT / Gemini / Perplexity consumer UIs."
    )

    def to_dict(self) -> dict[str, Any]:
        return {
            "model": self.model,
            "notes": self.notes,
            "conflict_count": len(self.conflicts),
            "checks": [c.to_dict() for c in self.checks],
            "conflicts": [c.to_dict() for c in self.conflicts],
            "label": "LLM-GENERATED (flags) over OBSERVED answers",
        }


_PROMPT = """You compare an OBSERVED AI-search answer against the CURRENT article Markdown.

Rules:
- Only flag conflicts where the OBSERVED answer asserts something that contradicts
  or invents specifics that CURRENT does not support (and CURRENT contradicts).
- Every conflict MUST include:
  - claim_from_observed_answer: a short verbatim quote from the OBSERVED answer
  - evidence_quote_from_current: a short verbatim quote from CURRENT that
    contradicts or fails to support that claim (must appear in CURRENT)
- Do NOT invent external world facts. Do NOT fact-check beyond CURRENT + OBSERVED.
- If no conflict, return an empty conflicts array.
- The prompt kind is {kind} (branded|factual).

Respond with JSON ONLY:
{{
  "conflicts": [
    {{
      "claim_from_observed_answer": "...",
      "evidence_quote_from_current": "...",
      "note": "brief why this is a conflict",
      "severity": "low|medium|high"
    }}
  ]
}}

PROMPT / QUERY:
{query}

OBSERVED ANSWER (DigitalOcean web_search API — not a consumer Chat UI):
---
{answer}
---

CURRENT.md:
---
{current}
---
"""


def _kind_for_query(query_text: str, queries: QuerySet | list[Query] | None) -> str:
    if queries is None:
        return "general"
    selected = queries.selected if isinstance(queries, QuerySet) else list(queries)
    for q in selected:
        text = q if isinstance(q, str) else q.text
        if text == query_text:
            return getattr(q, "kind", None) or "general"
    return "general"


def _validate_conflicts(
    raw: Any,
    *,
    query: str,
    answer: str,
    current: str,
) -> list[AccuracyConflict]:
    if isinstance(raw, dict):
        items = raw.get("conflicts") or []
    elif isinstance(raw, list):
        items = raw
    else:
        return []
    if not isinstance(items, list):
        return []

    out: list[AccuracyConflict] = []
    current_l = current
    answer_l = answer
    for item in items:
        if not isinstance(item, dict):
            continue
        claim = str(item.get("claim_from_observed_answer") or item.get("claim") or "").strip()
        evidence = str(
            item.get("evidence_quote_from_current") or item.get("evidence_quote") or ""
        ).strip()
        note = str(item.get("note") or "").strip()
        severity = str(item.get("severity") or "medium").strip().lower() or "medium"
        if severity not in {"low", "medium", "high"}:
            severity = "medium"
        if not claim or not evidence:
            continue
        # Plumbing: evidence must appear in CURRENT; claim should appear in answer.
        if evidence not in current_l:
            continue
        if claim not in answer_l:
            # Allow light normalize: collapse whitespace for membership
            claim_norm = " ".join(claim.split())
            answer_norm = " ".join(answer_l.split())
            if claim_norm not in answer_norm:
                continue
        out.append(
            AccuracyConflict(
                query=query,
                claim_from_observed_answer=claim,
                evidence_quote_from_current=evidence,
                note=note,
                severity=severity,
            )
        )
    return out


def evaluate_accuracy(
    article: Article,
    visibility: VisibilityReport,
    queries: QuerySet | list[Query] | None = None,
    *,
    client: SupportsRespondJSON | None = None,
    skip: bool = False,
) -> AccuracyReport:
    """Flag conflicts between OBSERVED answers and CURRENT for branded/factual prompts."""
    llm: SupportsRespondJSON = client or LLMClient()
    model = getattr(llm, "model", "") or ""

    if skip:
        return AccuracyReport(
            model=model,
            notes="Accuracy pass skipped.",
            checks=[],
            conflicts=[],
        )

    if not visibility.observations:
        return AccuracyReport(
            model=model,
            notes=(
                "No OBSERVED visibility rows — accuracy pass requires live "
                "DigitalOcean web_search answers."
            ),
        )

    if client is None and isinstance(llm, LLMClient) and not llm.available():
        raise LLMError("AEO_LLM_API_KEY required for brand-fact / accuracy pass")

    checks: list[AccuracyCheck] = []
    conflicts: list[AccuracyConflict] = []
    current = article.markdown

    for obs in visibility.observations:
        kind = _kind_for_query(obs.query, queries)
        if kind not in _ACCURACY_KINDS:
            checks.append(
                AccuracyCheck(
                    query=obs.query,
                    kind=kind,
                    skipped=True,
                    skip_reason="kind is not branded/factual",
                    observed_answer_preview=(obs.answer or "")[:400],
                )
            )
            continue
        if obs.error:
            checks.append(
                AccuracyCheck(
                    query=obs.query,
                    kind=kind,
                    skipped=True,
                    skip_reason=f"observation error: {obs.error}",
                )
            )
            continue
        if not (obs.answer or "").strip():
            checks.append(
                AccuracyCheck(
                    query=obs.query,
                    kind=kind,
                    skipped=True,
                    skip_reason="empty OBSERVED answer",
                )
            )
            continue

        raw = llm.respond_json(
            _PROMPT.format(
                kind=kind,
                query=obs.query,
                answer=obs.answer[:6000],
                current=current[:12000],
            ),
            max_output_tokens=2048,
        )
        found = _validate_conflicts(
            raw, query=obs.query, answer=obs.answer, current=current
        )
        conflicts.extend(found)
        checks.append(
            AccuracyCheck(
                query=obs.query,
                kind=kind,
                skipped=False,
                conflict_count=len(found),
                observed_answer_preview=(obs.answer or "")[:400],
            )
        )

    return AccuracyReport(
        checks=checks,
        conflicts=conflicts,
        model=model,
    )
