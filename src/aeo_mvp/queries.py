"""LLM question discovery + LLM quality validation.

Python only validates schema / length / dedupe / count (5–10).
No heading→question templates, token scoring, or SEO query banks.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Protocol

from aeo_mvp.article import Article
from aeo_mvp.llm import LLMClient, LLMError

MIN_QUESTIONS = 5
MAX_QUESTIONS = 10
MIN_Q_LEN = 12
MAX_Q_LEN = 220


class SupportsRespondJSON(Protocol):
    def respond_json(self, prompt: str, *, max_output_tokens: int = 4096) -> Any: ...

    @property
    def model(self) -> str: ...


@dataclass
class Query:
    text: str
    importance: str = "medium"
    reason: str = ""
    article_topics_or_evidence: str = ""
    source: str = "llm_generated"  # always LLM-generated here


@dataclass
class QuerySet:
    candidates: list[Query] = field(default_factory=list)
    selected: list[Query] = field(default_factory=list)
    quality_notes: str = ""
    model: str = ""

    @property
    def texts(self) -> list[str]:
        return [q.text for q in self.selected]


def _normalize_question(q: str) -> str:
    q = re.sub(r"\s+", " ", (q or "").strip())
    return q


def _dedupe_key(q: str) -> str:
    return re.sub(r"[^\w\s]", "", q.lower()).strip()


def validate_question_records(raw: Any) -> list[Query]:
    """Python plumbing: accept list or {questions: [...]} and validate fields."""
    if isinstance(raw, dict):
        items = raw.get("questions") or raw.get("selected") or raw.get("final") or []
    elif isinstance(raw, list):
        items = raw
    else:
        raise LLMError("Question discovery JSON must be a list or object with questions[]")

    if not isinstance(items, list):
        raise LLMError("questions must be a JSON array")

    out: list[Query] = []
    seen: set[str] = set()
    for item in items:
        if isinstance(item, str):
            text = _normalize_question(item)
            importance, reason, evidence = "medium", "", ""
        elif isinstance(item, dict):
            text = _normalize_question(
                str(item.get("question") or item.get("text") or "")
            )
            importance = str(item.get("importance") or "medium").strip() or "medium"
            reason = str(item.get("reason") or item.get("importance_reason") or "").strip()
            evidence = str(
                item.get("article_topics_or_evidence")
                or item.get("evidence")
                or item.get("topics")
                or ""
            ).strip()
        else:
            continue
        if not text or len(text) < MIN_Q_LEN or len(text) > MAX_Q_LEN:
            continue
        key = _dedupe_key(text)
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(
            Query(
                text=text,
                importance=importance,
                reason=reason,
                article_topics_or_evidence=evidence,
                source="llm_generated",
            )
        )
    return out


def clamp_questions(queries: list[Query]) -> list[Query]:
    """Keep at most MAX_QUESTIONS; raise if fewer than MIN after validation."""
    clipped = queries[:MAX_QUESTIONS]
    if len(clipped) < MIN_QUESTIONS:
        raise LLMError(
            f"Need {MIN_QUESTIONS}–{MAX_QUESTIONS} valid questions after validation; "
            f"got {len(clipped)}"
        )
    return clipped


_DISCOVER_PROMPT = """You are an Answer Engine query analyst.

Read the FULL Hashnode Markdown article below. Understand its topic, concepts,
entities, mechanisms, workflows, tradeoffs, examples, and claims.

Return ranked REALISTIC questions that a real user would ask an AI search engine
and that THIS article could meaningfully answer (or partially answer).

Rules:
- Return between 5 and 10 questions.
- Questions must be natural, specific, and grounded in the article.
- Do NOT invent heading transforms like "What is <heading>?" or "How does <heading> work?"
  when that would be awkward or artificial (e.g. "How does Repository work?").
- Avoid generic SEO bait, duplicates, and questions unrelated to the article.
- Prefer questions about mechanisms, decisions, tradeoffs, how-to steps, and concepts
  the article actually develops.

Respond with JSON ONLY:
{{
  "questions": [
    {{
      "question": "...",
      "importance": "high|medium|low",
      "reason": "why this question matters for answer engines",
      "article_topics_or_evidence": "brief pointer to topics/sections/claims in the article"
    }}
  ]
}}

ARTICLE MARKDOWN:
---
{article}
---
"""

_QUALITY_PROMPT = """You are validating AI-search questions for an Answer Engine Optimization review.

Given the FULL article and a candidate question list, evaluate each question for:
- realism (would a real user ask this?)
- relevance to the article
- importance for answer-engine visibility
- distinctness (not near-duplicates)
- answerability from the article (full or partial)
- specificity (not vague SEO filler)

Reject awkward heading transforms and unrelated questions.
Return a FINAL list of 5–10 best questions (may rewrite lightly for clarity,
but do not invent topics absent from the article).

Respond with JSON ONLY:
{{
  "questions": [
    {{
      "question": "...",
      "importance": "high|medium|low",
      "reason": "...",
      "article_topics_or_evidence": "..."
    }}
  ],
  "notes": "brief quality summary"
}}

ARTICLE MARKDOWN:
---
{article}
---

CANDIDATE QUESTIONS JSON:
{candidates}
"""


def discover_queries(
    article: Article,
    *,
    client: SupportsRespondJSON | None = None,
) -> QuerySet:
    """LLM generates candidates, LLM quality-validates; Python validates schema/count."""
    llm: SupportsRespondJSON = client or LLMClient()
    if client is None and isinstance(llm, LLMClient) and not llm.available():
        raise LLMError(
            "AEO_LLM_API_KEY required for LLM question discovery "
            "(no heuristic fallback)"
        )

    draft = llm.respond_json(
        _DISCOVER_PROMPT.format(article=article.markdown),
        max_output_tokens=4096,
    )
    candidates = validate_question_records(draft)
    if not candidates:
        raise LLMError("LLM returned no valid candidate questions")

    quality_raw = llm.respond_json(
        _QUALITY_PROMPT.format(
            article=article.markdown,
            candidates= _queries_json(candidates),
        ),
        max_output_tokens=4096,
    )
    selected = validate_question_records(quality_raw)
    selected = clamp_questions(selected)

    notes = ""
    if isinstance(quality_raw, dict):
        notes = str(quality_raw.get("notes") or "").strip()

    model = getattr(llm, "model", "") or ""
    return QuerySet(
        candidates=candidates,
        selected=selected,
        quality_notes=notes,
        model=model,
    )


def _queries_json(queries: list[Query]) -> str:
    import json

    return json.dumps(
        [
            {
                "question": q.text,
                "importance": q.importance,
                "reason": q.reason,
                "article_topics_or_evidence": q.article_topics_or_evidence,
            }
            for q in queries
        ],
        indent=2,
    )
