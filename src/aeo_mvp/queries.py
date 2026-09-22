"""Article-specific query discovery (no fixed universal production list)."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from aeo_mvp.article import Article
from aeo_mvp.config import get_settings

_TOKEN_RE = re.compile(r"[a-z0-9][a-z0-9+#.-]{2,}", re.I)
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
        "can",
        "does",
        "did",
        "not",
        "but",
        "you",
        "all",
        "any",
        "more",
        "than",
        "also",
        "just",
        "like",
        "such",
        "only",
        "each",
        "other",
        "some",
        "most",
        "over",
        "after",
        "before",
        "between",
        "through",
        "under",
        "again",
        "further",
        "then",
        "once",
        "here",
        "there",
        "these",
        "those",
        "should",
        "would",
        "could",
        "might",
        "must",
        "shall",
        "need",
        "build",
        "building",
    }
)


@dataclass
class Query:
    text: str
    source_section: str | None = None
    kind: str = "topic"  # topic | how_to | definition | comparison
    score: float = 0.0


@dataclass
class QuerySet:
    candidates: list[Query] = field(default_factory=list)
    selected: list[Query] = field(default_factory=list)

    @property
    def texts(self) -> list[str]:
        return [q.text for q in self.selected]


def _tokens(text: str) -> list[str]:
    out: list[str] = []
    for m in _TOKEN_RE.finditer(text or ""):
        t = m.group(0).lower().strip(".-")
        if len(t) < 3 or t in _STOP:
            continue
        if t not in out:
            out.append(t)
    return out


def _normalize_q(q: str) -> str:
    q = re.sub(r"\s+", " ", (q or "").strip())
    if q and q[-1] not in "?!.":
        q = q + "?"
    return q


def _candidate_from_heading(heading: str, title_tokens: list[str]) -> list[Query]:
    h = heading.strip()
    if not h or h.lower() == "introduction":
        return []
    # Skip pure code-y headings.
    if h.startswith("`") and h.endswith("`"):
        return []
    qs: list[Query] = []
    lower = h.lower()
    if lower.startswith(("what ", "how ", "why ", "when ", "where ", "who ")):
        qs.append(Query(text=_normalize_q(h), source_section=h, kind="topic", score=3.0))
        return qs
    # Definition / explanation
    qs.append(
        Query(
            text=_normalize_q(f"What is {h}"),
            source_section=h,
            kind="definition",
            score=2.5,
        )
    )
    qs.append(
        Query(
            text=_normalize_q(f"How does {h} work"),
            source_section=h,
            kind="how_to",
            score=2.2,
        )
    )
    if title_tokens:
        topic = " ".join(title_tokens[:4])
        qs.append(
            Query(
                text=_normalize_q(f"{h} in {topic}"),
                source_section=h,
                kind="topic",
                score=2.0,
            )
        )
    return qs


def _title_queries(title: str, intro: str) -> list[Query]:
    t = title.strip()
    if not t:
        return []
    qs = [
        Query(text=_normalize_q(f"What is {t}"), source_section=None, kind="definition", score=3.5),
        Query(text=_normalize_q(f"How to {t}"), source_section=None, kind="how_to", score=3.0),
        Query(
            text=_normalize_q(f"{t} explained"),
            source_section=None,
            kind="topic",
            score=2.8,
        ),
    ]
    # Pull a key phrase from intro first sentence.
    first = (intro or "").split(".")[0].strip()
    if 20 < len(first) < 140:
        qs.append(
            Query(
                text=_normalize_q(first),
                source_section=None,
                kind="topic",
                score=2.0,
            )
        )
    return qs


def discover_queries(article: Article, *, top_n: int | None = None) -> QuerySet:
    """Generate ~20–30 article-specific candidates, select ~15–20 with section coverage."""
    settings = get_settings()
    n = top_n if top_n is not None else settings.query_top_n
    n = max(8, min(25, int(n)))

    title_tokens = _tokens(article.title)[:6]
    candidates: list[Query] = []
    candidates.extend(_title_queries(article.title, article.intro))

    # Prefer non-H1 sections for coverage (avoid dumping everything on H1).
    body_sections = [s for s in article.sections if s.level >= 2] or list(article.sections)
    for sec in body_sections:
        candidates.extend(_candidate_from_heading(sec.heading, title_tokens))
        # Body-derived question: first declarative-ish sentence as "why/how"
        body_tokens = _tokens(sec.body)[:5]
        if body_tokens and sec.heading:
            phrase = " ".join(body_tokens[:4])
            candidates.append(
                Query(
                    text=_normalize_q(f"Why {phrase} for {sec.heading}"),
                    source_section=sec.heading,
                    kind="topic",
                    score=1.6,
                )
            )

    # Deduplicate by normalized text.
    seen: set[str] = set()
    unique: list[Query] = []
    for q in candidates:
        key = q.text.lower().rstrip("?").strip()
        if key in seen or len(key) < 8:
            continue
        seen.add(key)
        unique.append(q)

    # Cap candidates ~30.
    unique.sort(key=lambda q: (-q.score, q.text))
    candidates_capped = unique[:30]

    # Select with section coverage: round-robin by source_section.
    by_section: dict[str, list[Query]] = {}
    for q in candidates_capped:
        key = q.source_section or "__title__"
        by_section.setdefault(key, []).append(q)

    selected: list[Query] = []
    selected_keys: set[str] = set()
    # First pass: one per section for coverage.
    for _sec, qs in by_section.items():
        if len(selected) >= n:
            break
        pick = qs[0]
        k = pick.text.lower()
        if k not in selected_keys:
            selected.append(pick)
            selected_keys.add(k)
    # Fill remaining by score.
    for q in candidates_capped:
        if len(selected) >= n:
            break
        k = q.text.lower()
        if k in selected_keys:
            continue
        selected.append(q)
        selected_keys.add(k)

    return QuerySet(candidates=candidates_capped, selected=selected)
