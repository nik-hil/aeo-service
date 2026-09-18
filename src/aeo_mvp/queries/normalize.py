"""Query normalization and near-duplicate detection (query-discovery-v1)."""

from __future__ import annotations

import re
import unicodedata
from typing import Iterable, TypeVar

T = TypeVar("T")

JACCARD_NEAR_DUP = 0.85
TOKEN_RE = re.compile(r"[a-z0-9]+")


def normalize_query_text(text: str) -> str:
    """NFKC → lower → collapse whitespace."""
    s = unicodedata.normalize("NFKC", text or "")
    s = s.lower().strip()
    s = re.sub(r"\s+", " ", s)
    return s


def tokenize(text: str) -> set[str]:
    return set(TOKEN_RE.findall(normalize_query_text(text)))


def jaccard(a: set[str], b: set[str]) -> float:
    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0
    inter = len(a & b)
    union = len(a | b)
    return inter / union if union else 0.0


def is_near_duplicate(left: str, right: str, *, threshold: float = JACCARD_NEAR_DUP) -> bool:
    if normalize_query_text(left) == normalize_query_text(right):
        return True
    return jaccard(tokenize(left), tokenize(right)) >= threshold


def dedupe_by_text(
    items: list[T],
    *,
    text_fn,
    score_fn,
    id_fn,
    threshold: float = JACCARD_NEAR_DUP,
) -> list[T]:
    """Keep higher score, then lower id, when Jaccard ≥ threshold or exact norm match."""
    # Sort best-first so first kept wins
    ordered = sorted(items, key=lambda x: (-float(score_fn(x)), str(id_fn(x))))
    kept: list[T] = []
    kept_tokens: list[tuple[str, set[str]]] = []
    for item in ordered:
        text = text_fn(item)
        norm = normalize_query_text(text)
        toks = tokenize(text)
        dup = False
        for prev_norm, prev_toks in kept_tokens:
            if norm == prev_norm or jaccard(toks, prev_toks) >= threshold:
                dup = True
                break
        if dup:
            continue
        kept.append(item)
        kept_tokens.append((norm, toks))
    return kept


def one_per_topic_intent(
    items: list[T],
    *,
    topic_fn,
    intent_fn,
    score_fn,
    id_fn,
) -> list[T]:
    """Keep at most one candidate per (topic, intent), preferring higher score then lower id."""
    best: dict[tuple[str, str], T] = {}
    for item in items:
        key = (normalize_query_text(str(topic_fn(item) or "")), str(intent_fn(item)))
        if key not in best:
            best[key] = item
            continue
        cur = best[key]
        if (float(score_fn(item)), str(id_fn(cur))) > (
            float(score_fn(cur)),
            str(id_fn(item)),
        ):
            # higher score wins; on tie lower id wins (compare inverted)
            best[key] = item
        elif float(score_fn(item)) == float(score_fn(cur)) and str(id_fn(item)) < str(
            id_fn(cur)
        ):
            best[key] = item
    return sorted(best.values(), key=lambda x: (-float(score_fn(x)), str(id_fn(x))))
