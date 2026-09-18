"""Query normalization and near-duplicate detection.

Phase 3: NFKC + Jaccard ≥ 0.85.
Phase 4 additions (``lexical_jaccard_v1`` / ``simhash_v1``): lead-in strip for
equality, character 3-gram Dice, sorted token signature, optional simhash.
No paid embedding API required.
"""

from __future__ import annotations

import re
import unicodedata
from typing import Iterable, Literal, TypeVar

T = TypeVar("T")

JACCARD_NEAR_DUP = 0.85
CHAR_NGRAM_NEAR_DUP = 0.80
TOKEN_RE = re.compile(r"[a-z0-9]+")
LEAD_IN_RE = re.compile(
    r"^(what is|what are|how do i|how to|how does|how do|explain|key concepts in|"
    r"common pitfalls when working with)\s+",
    re.I,
)
DEDUP_METHOD_LEXICAL = "lexical_jaccard_v1"
DEDUP_METHOD_SIMHASH = "simhash_v1"

DedupMethod = Literal["lexical_jaccard_v1", "simhash_v1"]


def normalize_query_text(text: str) -> str:
    """NFKC → lower → collapse whitespace (Phase 3 contract)."""
    s = unicodedata.normalize("NFKC", text or "")
    s = s.lower().strip()
    s = re.sub(r"\s+", " ", s)
    return s


def normalize_for_equality(text: str) -> str:
    """Normalize plus strip trailing ?/. for equality / near-dup only."""
    return normalize_query_text(text).rstrip("?.").strip()


def strip_lead_ins(text: str) -> str:
    """Drop deterministic lead-ins for equality checks only (display text unchanged)."""
    s = normalize_for_equality(text)
    prev = None
    while prev != s:
        prev = s
        s = LEAD_IN_RE.sub("", s).strip()
    return s


def tokenize(text: str) -> set[str]:
    return set(TOKEN_RE.findall(normalize_query_text(text)))


def token_list(text: str) -> list[str]:
    return TOKEN_RE.findall(normalize_query_text(text))


def sorted_token_signature(text: str) -> str:
    return " ".join(sorted(tokenize(text)))


def jaccard(a: set[str], b: set[str]) -> float:
    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0
    inter = len(a & b)
    union = len(a | b)
    return inter / union if union else 0.0


def char_ngrams(text: str, n: int = 3) -> set[str]:
    s = normalize_query_text(text).replace(" ", "")
    if len(s) < n:
        return {s} if s else set()
    return {s[i : i + n] for i in range(len(s) - n + 1)}


def dice_coefficient(a: set[str], b: set[str]) -> float:
    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0
    inter = len(a & b)
    return (2.0 * inter) / (len(a) + len(b))


def is_near_duplicate(
    left: str,
    right: str,
    *,
    threshold: float = JACCARD_NEAR_DUP,
    char_ngram_threshold: float = CHAR_NGRAM_NEAR_DUP,
    use_char_ngrams: bool = True,
    use_lead_in_strip: bool = True,
) -> bool:
    if normalize_for_equality(left) == normalize_for_equality(right):
        return True
    if use_lead_in_strip and strip_lead_ins(left) == strip_lead_ins(right):
        if strip_lead_ins(left):  # empty after strip → not auto-dup
            return True
    if sorted_token_signature(left) == sorted_token_signature(right) and tokenize(left):
        return True
    if jaccard(tokenize(left), tokenize(right)) >= threshold:
        return True
    if use_char_ngrams:
        if dice_coefficient(char_ngrams(left), char_ngrams(right)) >= char_ngram_threshold:
            return True
    return False


def simhash64(text: str) -> int:
    """Simple 64-bit simhash over tokens (local CPU; no network)."""
    tokens = token_list(text)
    if not tokens:
        return 0
    bits = [0] * 64
    for tok in tokens:
        h = hash(tok) & ((1 << 64) - 1)
        # Mix further for stability across process hashes — use sha-like mix
        import hashlib

        h = int(hashlib.md5(tok.encode()).hexdigest()[:16], 16)
        for i in range(64):
            bits[i] += 1 if (h >> i) & 1 else -1
    out = 0
    for i, v in enumerate(bits):
        if v > 0:
            out |= 1 << i
    return out


def hamming_distance(a: int, b: int) -> int:
    return (a ^ b).bit_count()


def is_simhash_near_dup(left: str, right: str, *, max_distance: int = 3) -> bool:
    return hamming_distance(simhash64(left), simhash64(right)) <= max_distance


def dedupe_by_text(
    items: list[T],
    *,
    text_fn,
    score_fn,
    id_fn,
    threshold: float = JACCARD_NEAR_DUP,
    method: DedupMethod = DEDUP_METHOD_LEXICAL,
) -> list[T]:
    """Keep higher score, then lower id, when near-dup of an already-kept item."""
    ordered = sorted(items, key=lambda x: (-float(score_fn(x)), str(id_fn(x))))
    kept: list[T] = []
    kept_meta: list[tuple[str, set[str], str, int | None]] = []
    use_simhash = method == DEDUP_METHOD_SIMHASH
    for item in ordered:
        text = text_fn(item)
        norm = normalize_for_equality(text)
        toks = tokenize(text)
        sig = sorted_token_signature(text)
        sh = simhash64(text) if use_simhash else None
        dup = False
        for prev_norm, prev_toks, prev_sig, prev_sh in kept_meta:
            if norm == prev_norm or sig == prev_sig:
                dup = True
                break
            if jaccard(toks, prev_toks) >= threshold:
                dup = True
                break
            if dice_coefficient(char_ngrams(text), char_ngrams(prev_norm)) >= CHAR_NGRAM_NEAR_DUP:
                dup = True
                break
            if use_simhash and prev_sh is not None and sh is not None:
                if hamming_distance(sh, prev_sh) <= 3:
                    dup = True
                    break
        if dup:
            continue
        kept.append(item)
        kept_meta.append((norm, toks, sig, sh))
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
        if float(score_fn(item)) > float(score_fn(cur)):
            best[key] = item
        elif float(score_fn(item)) == float(score_fn(cur)) and str(id_fn(item)) < str(
            id_fn(cur)
        ):
            best[key] = item
    return sorted(best.values(), key=lambda x: (-float(score_fn(x)), str(id_fn(x))))
