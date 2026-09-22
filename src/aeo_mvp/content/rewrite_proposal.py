"""Evidence-grounded content rewrite proposals (deterministic / non-LLM).

The optimization layer builds a validated ``proposed`` replacement for
supported rewrite targets (currently: introduction / answer-first). The
Hashnode Markdown generator **applies** that proposal; it does not invent copy.

Rules (deterministic mode):
- MAY compress, combine, reorder, clarify, and rewrite existing facts into a
  more answerable form.
- MUST NOT invent facts, citations, URLs, unsupported numbers/claims/products/
  technologies/results.
- MUST NOT merely move a paragraph and call that a rewrite.
- Idempotent: already answer-first / already-matching proposed → no new proposal.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

_DEF_SENTENCE_RE = re.compile(
    r"\b(?:is|are|means|becomes|refers to|consists of)\b",
    re.I,
)
_INVENTED_FACT_RE = re.compile(
    r"\b(?:\d+(?:\.\d+)?%|\d{4}\s+(?:study|report)|according to|"
    r"research shows|studies show|cited? from)\b",
    re.I,
)
_URL_RE = re.compile(r"https?://[^\s)>\]]+", re.I)
_DIAGNOSTIC_RE = re.compile(
    r"\b(?:content gaps?|under-covered probes?|optimization brief|"
    r"edit[_ ]?ops?|page intelligence|aeo[_ ]?(?:service|mvp))\b",
    re.I,
)
_HTML_INJECT_RE = re.compile(
    r"</?(?:script|style|meta|link|html|head|body)[^>]*>", re.I
)
_BECOMES_WHEN_RE = re.compile(
    r"^(An?\s+)(.+?)\s+becomes\s+(an?\s+)?(.+?)\s+when\s+it\s+can\s+(.+)$",
    re.I | re.S,
)
_TEASER_RE = re.compile(
    r"\b(?:sounds?|seems?|appears?)\b.*\b(?:simple|easy|hard|complicated)\b"
    r"|\bthat is not really\b"
    r"|\bthat sounds complicated\b",
    re.I,
)

# Structural glue allowed in reformulations even if not in the source sentence.
_ALLOWED_GLUE = frozenset(
    {
        "a",
        "an",
        "the",
        "is",
        "are",
        "that",
        "can",
        "when",
        "and",
        "or",
        "to",
        "of",
        "for",
        "with",
        "from",
        "into",
        "toward",
        "towards",
        "their",
        "its",
        "based",
        "system",
        "systems",
        "ai",  # only when "AI agent" already appears in source corpus
    }
)

# Meaning-preserving clarifications applied only to definitional predicates.
_CLARIFY_SUBS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"\binvoke\b", re.I), "use"),
    (re.compile(r"\bthe result\b", re.I), "their results"),
    (re.compile(r"\bdecide to take actions\b", re.I), "decide when to take actions"),
    (
        re.compile(
            r"\bcontinue working until the task is complete\b",
            re.I,
        ),
        "continue working toward a task",
    ),
)


@dataclass
class RewriteProposal:
    """Validated rewrite payload attached to an edit op / change-plan item."""

    action: str = "rewrite"
    target: str = "introduction"
    original: str = ""
    proposed: str = ""
    evidence: list[str] = field(default_factory=list)
    reason: str = ""
    related_gap_ids: list[str] = field(default_factory=list)
    llm_used: bool = False
    paid_retrieval_used: bool = False
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "action": self.action,
            "target": self.target,
            "original": self.original,
            "proposed": self.proposed,
            "evidence": list(self.evidence),
            "reason": self.reason,
            "related_gap_ids": list(self.related_gap_ids),
            "llm_used": self.llm_used,
            "paid_retrieval_used": self.paid_retrieval_used,
        }


def _split_intro_blocks(md: str) -> tuple[str, list[str], str]:
    """Return (h1_line, intro paragraph blocks, remainder)."""
    lines = (md or "").splitlines()
    if not lines:
        return "", [], ""
    h1_idx = next((i for i, ln in enumerate(lines) if ln.startswith("# ")), None)
    if h1_idx is None:
        return "", [], md

    h1_line = lines[h1_idx]
    after = lines[h1_idx + 1 :]
    intro_lines: list[str] = []
    rest_start = 0
    in_fence = False
    for i, ln in enumerate(after):
        if ln.strip().startswith("```"):
            in_fence = not in_fence
            intro_lines.append(ln)
            continue
        if not in_fence and re.match(r"^#{1,6}\s+", ln):
            rest_start = i
            break
        intro_lines.append(ln)
    else:
        rest_start = len(after)

    blocks: list[str] = []
    buf: list[str] = []
    fence_buf: list[str] | None = None
    for ln in intro_lines:
        if ln.strip().startswith("```"):
            if fence_buf is None:
                if buf:
                    blocks.append("\n".join(buf).strip("\n"))
                    buf = []
                fence_buf = [ln]
            else:
                fence_buf.append(ln)
                blocks.append("\n".join(fence_buf))
                fence_buf = None
            continue
        if fence_buf is not None:
            fence_buf.append(ln)
            continue
        if not ln.strip():
            if buf:
                blocks.append("\n".join(buf).strip("\n"))
                buf = []
            continue
        buf.append(ln)
    if fence_buf is not None:
        blocks.append("\n".join(fence_buf))
    if buf:
        blocks.append("\n".join(buf).strip("\n"))

    remainder = "\n".join(after[rest_start:])
    return h1_line, blocks, remainder


def _score_definitional(text: str) -> float:
    t = (text or "").strip()
    if not t or t.startswith("```") or t.startswith("![") or t.startswith("|"):
        return -1.0
    if _TEASER_RE.search(t):
        return 0.0
    score = 0.0
    if _DEF_SENTENCE_RE.search(t):
        score += 3.0
    if re.search(r"\b(?:when|because|so that|in order to)\b", t, re.I):
        score += 1.5
    if t.endswith("."):
        score += 0.5
    words = len(t.split())
    if 12 <= words <= 60:
        score += 2.0
    elif 8 <= words < 12 or 60 < words <= 90:
        score += 1.0
    elif words < 6:
        score -= 1.0
    if t.endswith("?") and words < 20:
        score -= 1.5
    return score


def _content_tokens(text: str) -> set[str]:
    """Lowercased alphanumeric tokens excluding very short glue.

    Hyphenated compounds are expanded to both the full form and parts so
    grounded reformulations like ``LLM-based`` validate when ``llm`` and
    ``based`` are independently allowed.
    """
    out: set[str] = set()
    for t in re.findall(r"[a-z0-9]+(?:-[a-z0-9]+)*", (text or "").lower()):
        if len(t) <= 1:
            continue
        out.add(t)
        if "-" in t:
            for part in t.split("-"):
                if len(part) > 1:
                    out.add(part)
    return out


def _corpus_tokens(*parts: str) -> set[str]:
    out: set[str] = set()
    for p in parts:
        out |= _content_tokens(p)
    return out


def _clarify_predicate(pred: str) -> str:
    out = pred.strip()
    for pattern, repl in _CLARIFY_SUBS:
        out = pattern.sub(repl, out)
    out = re.sub(r"\s{2,}", " ", out).strip()
    return out


def _answer_first_reformulation(sentence: str, *, corpus: str) -> str | None:
    """Reformulate a definitional sentence into answer-first form.

    Only structural/clarify transforms; no new factual claims.
    """
    s = (sentence or "").strip()
    if not s:
        return None
    m = _BECOMES_WHEN_RE.match(s.rstrip("."))
    if not m:
        # Already answer-first-ish definitional lead — clarify in place only.
        clarified = _clarify_predicate(s)
        if clarified != s and _score_definitional(clarified) >= _score_definitional(s):
            return clarified if clarified.endswith((".", "!", "?")) else clarified + "."
        return None

    subject = m.group(2).strip()
    article_y = (m.group(3) or "an ").strip() + " "
    role = m.group(4).strip()
    predicate = _clarify_predicate(m.group(5).strip().rstrip("."))

    # Prefer "AI agent" when the article already uses that phrase.
    role_out = role
    if role.lower() == "agent" and re.search(r"\bai agent\b", corpus, re.I):
        role_out = "AI agent"
        article_y = "An "

    # "An LLM-based system" grounded when subject is LLM / language model.
    subject_l = subject.lower()
    if subject_l in {"llm", "llms", "large language model", "large language models"}:
        subject_phrase = "LLM-based system"
    else:
        subject_phrase = f"{subject}-based system"

    proposed = (
        f"{article_y.strip().capitalize()} {role_out} is an {subject_phrase} "
        f"that can {predicate}."
    )
    proposed = re.sub(r"\s{2,}", " ", proposed).strip()
    # Fix "An An" / double articles from capitalize edge cases.
    proposed = re.sub(r"^(An|A)\s+\1\s+", r"\1 ", proposed, flags=re.I)
    if not proposed[0].isupper():
        proposed = proposed[0].upper() + proposed[1:]
    return proposed


def validate_proposed_rewrite(
    *,
    proposed: str,
    original: str,
    evidence: list[str],
    source_markdown: str,
    h1: str | None = None,
) -> list[str]:
    """Return warning codes; empty list means safe to apply."""
    warnings: list[str] = []
    prop = (proposed or "").strip()
    if not prop:
        return ["proposed_empty"]
    if prop == (original or "").strip():
        return ["proposed_identical_to_original"]
    if _HTML_INJECT_RE.search(prop):
        warnings.append("proposed_html_injection")
    if _DIAGNOSTIC_RE.search(prop):
        warnings.append("proposed_diagnostic_leak")
    if h1 and prop.lstrip().startswith(f"# {h1}"):
        warnings.append("proposed_includes_h1")
    if re.search(r"^#\s+", prop, re.M):
        # Headings inside proposed intro are not supported for intro rewrite.
        warnings.append("proposed_contains_heading")

    # URLs in proposed must already exist in source.
    src_urls = {u.rstrip(".,);") for u in _URL_RE.findall(source_markdown or "")}
    for url in _URL_RE.findall(prop):
        if url.rstrip(".,);") not in src_urls:
            warnings.append("proposed_invented_url")
            break

    # Invented-fact patterns only allowed if already present in source/evidence.
    corpus = "\n".join([source_markdown or "", original or "", *evidence])
    for m in _INVENTED_FACT_RE.finditer(prop):
        frag = m.group(0)
        if frag.lower() not in corpus.lower():
            warnings.append("proposed_invented_fact")
            break

    # Token grounding: every content token must appear in evidence∪source∪allowed glue
    # (plus clarify-substitution outputs that map from source tokens).
    allowed = _corpus_tokens(corpus) | _ALLOWED_GLUE
    # Synonym outputs from clarify map are allowed when source had the input form.
    if re.search(r"\binvoke\b", corpus, re.I):
        allowed.add("use")
    if re.search(r"\bthe result\b", corpus, re.I):
        allowed.update({"their", "results"})
    if re.search(r"\bdecide to take actions\b", corpus, re.I):
        allowed.add("when")
    if re.search(r"\buntil the task is complete\b", corpus, re.I):
        allowed.update({"toward", "towards"})
    if re.search(r"\bai agent\b", corpus, re.I):
        allowed.add("ai")
    if re.search(r"\bllm\b", corpus, re.I):
        allowed.update({"llm", "based", "system"})

    def _token_grounded(tok: str) -> bool:
        if tok in allowed:
            return True
        if "-" in tok and all(
            (p in allowed or len(p) <= 1) for p in tok.split("-")
        ):
            return True
        return False

    unknown = {t for t in _content_tokens(prop) if not _token_grounded(t)}
    if unknown:
        warnings.append("proposed_ungrounded_tokens:" + ",".join(sorted(unknown)[:8]))

    # Must be meaningfully different from a pure paragraph move of `original`.
    # If proposed is an exact substring of original (or vice versa equal block),
    # reject as reorder-only unless reformulation markers present.
    if prop in (original or "") or (original or "").strip() == prop:
        warnings.append("proposed_is_reorder_only")
    return warnings


def _pick_definitional_evidence(
    intro_blocks: list[str],
    *,
    body: str,
    pi: dict[str, Any],
) -> tuple[str | None, list[str]]:
    """Pick best definitional evidence sentence/paragraph from source only."""
    candidates: list[tuple[float, str]] = []
    evidence_pool: list[str] = []

    for block in intro_blocks:
        if block.startswith("```"):
            continue
        evidence_pool.append(block.strip())
        score = _score_definitional(block)
        if score >= 0:
            candidates.append((score, block.strip()))
        for sent in re.split(r"(?<=[.!?])\s+", block.strip()):
            sent = sent.strip()
            if len(sent.split()) < 8:
                continue
            s_score = _score_definitional(sent)
            if s_score > 1.0:
                candidates.append((s_score, sent))
                evidence_pool.append(sent)

    for block in pi.get("answer_blocks") or []:
        if not isinstance(block, dict):
            continue
        snippet = str(block.get("snippet") or block.get("text") or "").strip()
        if not snippet or len(snippet) < 24:
            continue
        if snippet not in (body or "") and snippet not in "\n".join(intro_blocks):
            continue
        candidates.append((_score_definitional(snippet) + 0.5, snippet))
        evidence_pool.append(snippet)

    if not candidates:
        return None, []
    candidates.sort(key=lambda x: (-x[0], len(x[1])))
    best_score, best = candidates[0]
    if best_score < 1.0:
        return None, []
    # De-dupe evidence preserving order.
    seen: set[str] = set()
    evidence: list[str] = []
    for e in evidence_pool:
        key = e.strip()
        if not key or key in seen:
            continue
        seen.add(key)
        evidence.append(key)
        if len(evidence) >= 6:
            break
    return best.strip(), evidence


def _is_already_answer_first(intro_blocks: list[str]) -> bool:
    if not intro_blocks:
        return False
    first = intro_blocks[0].strip()
    if _TEASER_RE.search(first):
        return False
    return _score_definitional(first) >= 4.0


def _build_proposed_intro(
    *,
    intro_blocks: list[str],
    lead_source: str,
    lead_proposed: str,
) -> str:
    """Compose full intro replacement: rewritten lead + retained grounded context."""
    remaining: list[str] = []
    for block in intro_blocks:
        if block.startswith("```"):
            remaining.append(block)
            continue
        stripped = block.strip()
        if not stripped:
            continue
        # Drop the source lead paragraph/sentence we reformulated.
        if stripped == lead_source.strip():
            continue
        if lead_source.strip() in stripped and not block.startswith("```"):
            trimmed = stripped.replace(lead_source.strip(), "", 1).strip()
            trimmed = re.sub(r"\s{2,}", " ", trimmed).strip()
            if trimmed:
                remaining.append(trimmed)
            continue
        # Drop pure teaser openers that the rewrite supersedes.
        if _TEASER_RE.search(stripped) and len(stripped.split()) < 20:
            continue
        # Drop short non-definitional stingers superseded by the answer-first lead
        # (generic — not article-specific copy). Keep media, lists, quotes, URLs.
        words = len(stripped.split())
        if (
            words <= 16
            and _score_definitional(stripped) < 2.0
            and not stripped.startswith(("```", "![", "[", "|", ">", "-", "*"))
            and not _URL_RE.search(stripped)
        ):
            continue
        remaining.append(stripped)

    parts = [lead_proposed.strip()] + remaining
    return "\n\n".join(p for p in parts if p).strip()


def propose_introduction_rewrite(
    *,
    source_markdown: str,
    page_intelligence: dict[str, Any] | None = None,
    reason: str = "Answer-first introduction grounded in page evidence.",
    related_gap_ids: list[str] | None = None,
    force: bool = False,
) -> RewriteProposal | None:
    """Build an evidence-grounded intro rewrite proposal from source Markdown.

    Returns None when no grounded rewrite is warranted (already answer-first,
    insufficient evidence, or validation failure).
    """
    pi = page_intelligence or {}
    h1_line, intro_blocks, _remainder = _split_intro_blocks(source_markdown)
    if not h1_line or not intro_blocks:
        return None

    h1 = h1_line[2:].strip() if h1_line.startswith("# ") else None
    original = "\n\n".join(intro_blocks).strip()

    if not force and _is_already_answer_first(intro_blocks):
        # Idempotence: already answer-first → no rewrite churn.
        return None

    lead_source, evidence = _pick_definitional_evidence(
        intro_blocks, body=source_markdown, pi=pi
    )
    if not lead_source:
        return None

    corpus = source_markdown
    lead_proposed = _answer_first_reformulation(lead_source, corpus=corpus)
    if not lead_proposed:
        # Fall back: still require a semantic rewrite, not a move.
        # If we cannot reformulate, refuse rather than reorder-only.
        return None

    if lead_proposed.strip() == lead_source.strip():
        return None

    proposed_intro = _build_proposed_intro(
        intro_blocks=intro_blocks,
        lead_source=lead_source,
        lead_proposed=lead_proposed,
    )
    if not proposed_intro or proposed_intro.strip() == original.strip():
        return None

    # Ensure evidence includes the definitional source sentence.
    if lead_source not in evidence:
        evidence = [lead_source, *evidence]

    val_warnings = validate_proposed_rewrite(
        proposed=proposed_intro,
        original=original,
        evidence=evidence,
        source_markdown=source_markdown,
        h1=h1,
    )
    # Soft: ungrounded token warning is hard-fail; reorder-only hard-fail.
    hard = [
        w
        for w in val_warnings
        if w
        in {
            "proposed_empty",
            "proposed_identical_to_original",
            "proposed_html_injection",
            "proposed_diagnostic_leak",
            "proposed_includes_h1",
            "proposed_contains_heading",
            "proposed_invented_url",
            "proposed_invented_fact",
            "proposed_is_reorder_only",
        }
        or w.startswith("proposed_ungrounded_tokens:")
    ]
    if hard:
        return None

    return RewriteProposal(
        action="rewrite",
        target="introduction",
        original=original,
        proposed=proposed_intro,
        evidence=evidence,
        reason=reason,
        related_gap_ids=list(related_gap_ids or []),
        llm_used=False,
        paid_retrieval_used=False,
        warnings=list(val_warnings),
    )


def _is_intro_target(target: str, *, h1: str | None, instruction: str = "") -> bool:
    t = (target or "").strip()
    key = t.lower()
    instr = (instruction or "").lower()
    if key in {"introduction", "intro", "opening"}:
        return True
    if "answer-first" in instr or "answer first" in instr:
        return True
    if "introduction" in instr:
        return True
    if key.startswith("section:") and h1:
        section_name = t.split(":", 1)[1].strip()
        if section_name.lower() == h1.lower():
            return True
    return False


def enrich_ops_with_rewrite_proposals(
    ops: list[dict[str, Any]],
    *,
    source_markdown: str,
    page_intelligence: dict[str, Any] | None = None,
    h1: str | None = None,
) -> tuple[list[dict[str, Any]], RewriteProposal | None, list[str]]:
    """Content-optimization layer: generate + attach rewrite proposals onto ops.

    Ownership boundary: this function belongs to the content optimization layer.
    Platform Markdown generators must **consume** already-enriched ops and must
    not call this (or ``propose_introduction_rewrite``) to invent copy.

    Steps: identify intro rewrite targets → build evidence-grounded ``proposed``
    → validate → attach ``original`` / ``proposed`` / ``evidence`` /
    ``related_gap_ids`` / ``reason`` on the edit op.

    Returns (enriched_ops, proposal_or_none, warnings).
    Ops that already carry a non-empty ``proposed`` are validated only (not
    regenerated).
    """
    warnings: list[str] = []
    if not ops:
        return ops, None, warnings

    pi = page_intelligence or {}
    resolved_h1 = h1 or str(pi.get("h1") or pi.get("title") or "").strip() or None
    if not resolved_h1:
        m = re.search(r"^#\s+(.+)$", source_markdown or "", re.M)
        if m:
            resolved_h1 = m.group(1).strip()

    enriched: list[dict[str, Any]] = []
    proposal: RewriteProposal | None = None

    for op in ops:
        if not isinstance(op, dict):
            continue
        action = str(op.get("action") or "").strip().lower()
        target = str(
            op.get("target")
            or op.get("target_locator")
            or op.get("anchor_locator")
            or ""
        ).strip()
        instruction = str(
            op.get("instruction") or op.get("reason") or op.get("notes") or ""
        ).strip()
        related = list(op.get("related_gap_ids") or [])

        existing_proposed = op.get("proposed")
        if (
            action in {"rewrite", "expand", "add"}
            and _is_intro_target(target, h1=resolved_h1, instruction=instruction)
            and isinstance(existing_proposed, str)
            and existing_proposed.strip()
        ):
            # Caller-supplied proposal — validate only.
            original = str(op.get("original") or "").strip()
            evidence = [str(e) for e in (op.get("evidence") or []) if str(e).strip()]
            val = validate_proposed_rewrite(
                proposed=existing_proposed,
                original=original or existing_proposed,
                evidence=evidence,
                source_markdown=source_markdown,
                h1=resolved_h1,
            )
            hard = [
                w
                for w in val
                if w
                in {
                    "proposed_empty",
                    "proposed_html_injection",
                    "proposed_diagnostic_leak",
                    "proposed_includes_h1",
                    "proposed_invented_url",
                    "proposed_invented_fact",
                }
                or w.startswith("proposed_ungrounded_tokens:")
            ]
            if hard:
                warnings.extend(hard)
                # Strip invalid proposed so generator skips apply.
                cleaned = {**op, "proposed": None}
                enriched.append(cleaned)
                continue
            proposal = RewriteProposal(
                action="rewrite",
                target="introduction",
                original=original,
                proposed=existing_proposed.strip(),
                evidence=evidence,
                reason=instruction,
                related_gap_ids=related,
            )
            enriched.append(op)
            continue

        if action in {"rewrite", "expand"} and _is_intro_target(
            target, h1=resolved_h1, instruction=instruction
        ):
            if proposal is None:
                proposal = propose_introduction_rewrite(
                    source_markdown=source_markdown,
                    page_intelligence=pi,
                    reason=instruction
                    or "Answer-first introduction grounded in page evidence.",
                    related_gap_ids=related,
                )
            if proposal is None:
                warnings.append("intro_rewrite_no_grounded_proposal")
                enriched.append(op)
                continue
            row = {
                **op,
                "action": "rewrite",
                "target": op.get("target") or op.get("target_locator") or "introduction",
                "original": proposal.original,
                "proposed": proposal.proposed,
                "evidence": list(proposal.evidence),
                "reason": proposal.reason or instruction,
                "related_gap_ids": list(proposal.related_gap_ids or related),
            }
            # Keep EditOp wire keys when present.
            if op.get("target_locator") and not op.get("target"):
                row["target_locator"] = op.get("target_locator")
            if op.get("instruction") and not row.get("instruction"):
                row["instruction"] = op.get("instruction")
            enriched.append(row)
            continue

        enriched.append(op)

    return enriched, proposal, warnings
