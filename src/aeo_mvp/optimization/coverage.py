"""Query/topic coverage vs page content (≠ AI visibility metrics)."""

from __future__ import annotations

import re
from typing import Any, Iterable

from aeo_mvp.optimization.models import CoverageLevel, PageIntelligence, QueryCoverageRow

_TOKEN_RE = re.compile(r"[a-z0-9][a-z0-9+#-]{1,}", re.I)
_STOP = frozenset(
    {
        "the",
        "and",
        "for",
        "with",
        "from",
        "this",
        "that",
        "your",
        "our",
        "into",
        "about",
        "using",
        "have",
        "will",
        "are",
        "was",
        "were",
        "been",
        "being",
        "their",
        "they",
        "them",
        "what",
        "when",
        "where",
        "which",
        "while",
        "how",
        "who",
        "why",
        "a",
        "an",
        "of",
        "to",
        "in",
        "on",
        "at",
        "by",
        "or",
        "as",
        "is",
        "it",
        "be",
        "vs",
        "versus",
    }
)


def _tokens(text: str | None) -> set[str]:
    if not text:
        return set()
    return {
        t.lower()
        for t in _TOKEN_RE.findall(text)
        if len(t) > 2 and t.lower() not in _STOP
    }


def _page_blob(page: PageIntelligence) -> str:
    parts = [
        page.title or "",
        page.meta_description or "",
        page.h1 or "",
        " ".join(h.text for h in page.headings),
        " ".join(page.topics),
        " ".join(page.entities),
        " ".join(page.faq_coverage.get("question_headings") or []),
    ]
    return " ".join(parts).lower()


def coverage_level(
    query_text: str,
    page: PageIntelligence,
    *,
    topic: str | None = None,
    entity: str | None = None,
) -> tuple[CoverageLevel, list[str]]:
    """Deterministic coverage: direct | partial | mention | none.

    Separate from AI-search / LLM-mention visibility rates.
    """
    blob = _page_blob(page)
    q_tokens = _tokens(query_text)
    matched: list[str] = []
    if not q_tokens:
        return "none", matched

    # Exact phrase (normalized whitespace)
    phrase = re.sub(r"\s+", " ", (query_text or "").strip().lower())
    if len(phrase) >= 8 and phrase in blob:
        matched.append("exact_phrase")
        return "direct", matched

    hit = sorted(t for t in q_tokens if t in blob)
    matched.extend(hit)
    ratio = len(hit) / max(len(q_tokens), 1)

    topic_hit = False
    if topic:
        ttoks = _tokens(topic)
        if ttoks and ttoks.issubset(_tokens(blob)):
            topic_hit = True
            matched.append(f"topic:{topic}")
        elif topic.lower() in blob:
            topic_hit = True
            matched.append(f"topic_mention:{topic}")

    entity_hit = False
    if entity and entity.lower() in blob:
        entity_hit = True
        matched.append(f"entity:{entity}")

    if ratio >= 0.75 and (topic_hit or entity_hit or len(hit) >= 3):
        return "direct", matched
    if ratio >= 0.45 or (topic_hit and ratio >= 0.25):
        return "partial", matched
    if ratio > 0 or topic_hit or entity_hit:
        return "mention", matched
    return "none", matched


def _iter_queries(queryset: Any) -> list[dict[str, Any]]:
    """Accept QuerySet object, dict, or list of query dicts."""
    if queryset is None:
        return []
    if isinstance(queryset, list):
        out = []
        for i, item in enumerate(queryset):
            if isinstance(item, dict):
                out.append(item)
            elif hasattr(item, "to_dict"):
                out.append(item.to_dict())
            else:
                out.append({"query_id": f"q_{i}", "text": str(item)})
        return out
    if hasattr(queryset, "members"):
        rows = []
        for m in queryset.members:
            q = m.query if hasattr(m, "query") else m
            rows.append(
                {
                    "query_id": getattr(q, "query_id", None) or (q.get("query_id") if isinstance(q, dict) else None),
                    "text": getattr(q, "text", None) or (q.get("text") if isinstance(q, dict) else str(q)),
                    "intent": getattr(q, "intent", None) if not isinstance(q, dict) else q.get("intent"),
                    "topic": getattr(q, "topic", None) if not isinstance(q, dict) else q.get("topic"),
                    "entity": getattr(q, "entity", None) if not isinstance(q, dict) else q.get("entity"),
                }
            )
        return rows
    if isinstance(queryset, dict):
        members = queryset.get("members") or queryset.get("queries") or []
        rows = []
        for m in members:
            if not isinstance(m, dict):
                continue
            q = m.get("query") if isinstance(m.get("query"), dict) else m
            rows.append(
                {
                    "query_id": q.get("query_id") or q.get("id"),
                    "text": q.get("text") or q.get("query"),
                    "intent": q.get("intent"),
                    "topic": q.get("topic"),
                    "entity": q.get("entity"),
                }
            )
        return rows
    return []


def assess_query_coverage(
    page: PageIntelligence,
    queryset: Any,
) -> list[QueryCoverageRow]:
    rows: list[QueryCoverageRow] = []
    for q in _iter_queries(queryset):
        text = (q.get("text") or "").strip()
        qid = q.get("query_id") or q.get("id") or f"q_{len(rows)}"
        level, matched = coverage_level(
            text,
            page,
            topic=q.get("topic"),
            entity=q.get("entity"),
        )
        note = {
            "direct": "Query concepts appear substantively on page",
            "partial": "Partial lexical/topic overlap",
            "mention": "Weak mention only",
            "none": "No detectable coverage on page",
        }[level]
        rows.append(
            QueryCoverageRow(
                query_id=str(qid),
                query_text=text,
                intent=q.get("intent"),
                topic=q.get("topic"),
                coverage=level,
                matched_signals=matched,
                note=note,
            )
        )
    # Stable sort: coverage severity then query_id
    order = {"none": 0, "mention": 1, "partial": 2, "direct": 3}
    rows.sort(key=lambda r: (order[r.coverage], r.query_id, r.query_text.lower()))
    return rows


def summarize_coverage(rows: Iterable[QueryCoverageRow]) -> dict[str, int]:
    summary = {"direct": 0, "partial": 0, "mention": 0, "none": 0}
    for r in rows:
        summary[r.coverage] = summary.get(r.coverage, 0) + 1
    return summary
