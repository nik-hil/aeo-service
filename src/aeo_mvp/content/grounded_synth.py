"""Grounded proposed-change synthesis for AEO question opportunities.

Only emits ``proposed_change`` text that is fully grounded in validated
article evidence. Never invents facts, stats, URLs, or entities.

Ownership: content optimization layer. Callers must not invent a second rewriter.
"""

from __future__ import annotations

import re
from typing import Literal

GroundingStatus = Literal[
    "SAFE_TO_GENERATE",
    "REQUIRES_NEW_INFORMATION",
    "REJECTED_UNGROUNDED",
]

_WS_RE = re.compile(r"\s+")
_TOKEN_RE = re.compile(r"[a-z0-9][a-z0-9+#-]{1,}", re.I)
_INVENTED_FACT_RE = re.compile(
    r"\b\d+(?:\.\d+)?%|\b(?:https?://|www\.)\S+",
    re.I,
)
_URL_RE = re.compile(r"https?://[^\s)>\]]+", re.I)
_HTML_INJECT_RE = re.compile(r"<\s*(script|iframe|object|embed|link|style)\b", re.I)
_ALLOWED_GLUE = frozenset(
    {
        "a", "an", "the", "and", "or", "to", "of", "in", "on", "for", "with",
        "is", "are", "as", "by", "from", "that", "this", "it", "be", "can",
        "may", "when", "how", "what", "why", "who", "which", "into", "about",
    }
)


def ws_canonical(text: str) -> str:
    """Whitespace-canonical form for evidence substring checks."""
    return _WS_RE.sub(" ", (text or "").strip()).lower()


def evidence_quote_in_article(quote: str, article_text: str) -> bool:
    """True when quote appears verbatim under WS-canonical matching."""
    q = ws_canonical(quote)
    if len(q) < 12:
        return False
    return q in ws_canonical(article_text)


def validate_evidence_list(
    evidence: list[str], article_text: str
) -> tuple[list[str], list[str]]:
    """Keep only quotes present in article; return (kept, rejected)."""
    kept: list[str] = []
    rejected: list[str] = []
    for raw in evidence or []:
        quote = (raw or "").strip()
        if not quote:
            continue
        if evidence_quote_in_article(quote, article_text):
            kept.append(quote)
        else:
            rejected.append(quote)
    return kept, rejected


def _content_tokens(text: str) -> set[str]:
    return {t.lower() for t in _TOKEN_RE.findall(text or "") if len(t) > 1}


def _proposed_invents_facts(proposed: str, article_text: str) -> bool:
    corpus = ws_canonical(article_text)
    for m in _INVENTED_FACT_RE.finditer(proposed or ""):
        frag = ws_canonical(m.group(0))
        if frag and frag not in corpus:
            return True
    src_urls = {u.rstrip(".,);") for u in _URL_RE.findall(article_text or "")}
    for url in _URL_RE.findall(proposed or ""):
        if url.rstrip(".,);") not in src_urls:
            return True
    return False


def _token_grounded(proposed: str, *, article_text: str, evidence: list[str], question: str) -> bool:
    corpus = "\n".join([article_text or "", question or "", *evidence])
    allowed = _content_tokens(corpus) | _ALLOWED_GLUE
    unknown = {t for t in _content_tokens(proposed) if t not in allowed}
    return not unknown


def synthesize_proposed_change(
    *,
    question: str,
    evidence: list[str],
    article_text: str,
    answerability: str,
) -> tuple[str | None, GroundingStatus, list[str]]:
    """Build a safe proposed change from validated evidence only.

    Returns ``(proposed_change | None, grounding_status, warnings)``.

    - Missing answerability / no evidence → ``REQUIRES_NEW_INFORMATION``, no text.
    - Ungrounded / invented content → ``REJECTED_UNGROUNDED``, no text.
    - Otherwise → ``SAFE_TO_GENERATE`` with grounded FAQ-style Markdown.
    """
    warnings: list[str] = []
    kept, rejected = validate_evidence_list(list(evidence or []), article_text)
    if rejected:
        warnings.append(f"evidence_rejected:{len(rejected)}")

    if answerability == "missing" or not kept:
        return None, "REQUIRES_NEW_INFORMATION", warnings

    q = (question or "").strip() or "Question"
    lines = [f"**Q:** {q}", ""]
    for quote in kept[:3]:
        cleaned = _WS_RE.sub(" ", quote.strip())
        if not cleaned.endswith((".", "!", "?")):
            cleaned = cleaned + "."
        lines.append(cleaned)
    proposed = "\n".join(lines).strip() + "\n"

    if not proposed.strip():
        return None, "REQUIRES_NEW_INFORMATION", warnings + ["proposed_empty"]
    if _HTML_INJECT_RE.search(proposed):
        return None, "REJECTED_UNGROUNDED", warnings + ["proposed_html_injection"]
    if _proposed_invents_facts(proposed, article_text):
        return None, "REJECTED_UNGROUNDED", warnings + ["proposed_invented_fact"]
    if not _token_grounded(
        proposed, article_text=article_text, evidence=kept, question=q
    ):
        return None, "REJECTED_UNGROUNDED", warnings + ["proposed_ungrounded_tokens"]

    return proposed, "SAFE_TO_GENERATE", warnings
