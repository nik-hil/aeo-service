"""Generate a complete recommended Markdown draft for Hashnode workflows.

Output is labeled **RECOMMENDED MARKDOWN** — never a final/guaranteed AEO article.
Preserves useful current content; does not invent facts or emit HTML-only constructs.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

_H1_RE = re.compile(r"^#\s+(.+)$", re.MULTILINE)
_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+)$", re.MULTILINE)
_HTML_TAG_RE = re.compile(r"</?(?:script|style|meta|link|html|head|body)[^>]*>", re.I)

_DISCLAIMER = (
    "**RECOMMENDED MARKDOWN** — a suggested draft for the Hashnode editor, "
    "GitHub publish, or bulk import. Not a final or guaranteed AEO article. "
    "Replacing the public `.md` URL does not edit the published post by itself."
)


@dataclass
class RecommendedMarkdown:
    body: str
    ok: bool
    title: str | None = None
    warnings: list[str] = field(default_factory=list)
    generator: str = "hashnode_recommended_markdown_v1"


def _strip_html_only(text: str) -> str:
    """Remove HTML-only constructs authors cannot control in Hashnode Markdown."""
    out = _HTML_TAG_RE.sub("", text or "")
    # Drop JSON-LD style blocks if somehow present.
    out = re.sub(
        r"```(?:json|jsonld)?\s*\{[^{}]*\"@context\"[^{}]*\}```",
        "",
        out,
        flags=re.I | re.S,
    )
    return out


def _extract_title(md: str, fallback: str | None = None) -> str | None:
    m = _H1_RE.search(md or "")
    if m:
        return m.group(1).strip()[:200] or fallback
    return fallback


def _heading_texts(md: str) -> list[str]:
    return [m.group(2).strip() for m in _HEADING_RE.finditer(md or "")]


def _ensure_answer_first(md: str, lead: str | None) -> str:
    """If opening is empty after H1, insert a short lead from observed signals."""
    if not lead or not lead.strip():
        return md
    lines = (md or "").splitlines()
    if not lines:
        return f"# Untitled\n\n{lead.strip()}\n"
    # Find first H1 and content after it
    idx = next((i for i, ln in enumerate(lines) if ln.startswith("# ")), None)
    if idx is None:
        return md
    # Skip blank lines after H1
    j = idx + 1
    while j < len(lines) and not lines[j].strip():
        j += 1
    # If next content is already a paragraph (not a heading), keep as-is
    if j < len(lines) and not lines[j].startswith("#"):
        return md
    insert = ["", lead.strip(), ""]
    return "\n".join(lines[: idx + 1] + insert + lines[idx + 1 :])


def _ensure_faq_section(md: str, questions: list[str]) -> str:
    if not questions:
        return md
    lower = (md or "").lower()
    if "faq" in lower or "frequently asked" in lower:
        return md
    parts = [md.rstrip(), "", "## FAQ", ""]
    for q in questions[:5]:
        q = (q or "").strip()
        if not q:
            continue
        if not q.endswith("?"):
            q = f"{q}?"
        parts.append(f"### {q}")
        parts.append("")
        parts.append(
            "_Add a concise, factual answer grounded in this article — "
            "do not invent unsupported claims._"
        )
        parts.append("")
    return "\n".join(parts).rstrip() + "\n"


def _ensure_howto_steps(md: str) -> str:
    lower = (md or "").lower()
    if re.search(r"^\d+\.\s+", md or "", re.M) or "step-by-step" in lower:
        return md
    if "## " not in (md or ""):
        return md
    # Light touch: append a steps scaffold only when brief/gaps asked for howto.
    return (
        md.rstrip()
        + "\n\n## Steps\n\n"
        + "1. _Describe the first concrete step from this article._\n"
        + "2. _Describe the next step without inventing tools or results._\n"
        + "3. _Describe the final verification step._\n"
    )


def generate_recommended_markdown(
    *,
    source_markdown: str | None,
    page_intelligence: dict[str, Any] | None = None,
    brief: dict[str, Any] | None = None,
    gaps: list[dict[str, Any]] | None = None,
    recommendations: list[dict[str, Any]] | None = None,
    title_hint: str | None = None,
) -> RecommendedMarkdown:
    """Build a complete recommended Markdown draft from current MD + evidence.

    Returns ``ok=False`` with an honest message when no meaningful draft can be made.
    Never fabricates product facts; never labels the result as final/guaranteed.
    """
    raw = (source_markdown or "").strip()
    if not raw:
        return RecommendedMarkdown(
            body=(
                f"{_DISCLAIMER}\n\n"
                "_No source Markdown was preserved for this page, so a recommended "
                "draft cannot be generated without fabricating content._\n"
            ),
            ok=False,
            title=title_hint,
            warnings=["no_source_markdown"],
        )

    pi = page_intelligence or {}
    brief = brief or {}
    gap_rows = list(gaps or [])
    rec_codes = {
        str(r.get("code") or "")
        for r in (recommendations or [])
        if isinstance(r, dict)
    }
    for g in gap_rows:
        if isinstance(g, dict) and g.get("gap_type"):
            # Map common gap types into soft improvement signals
            gt = str(g.get("gap_type") or "").lower()
            if "answer" in gt:
                rec_codes.add("REC_ADD_ANSWER_FIRST")
            if "faq" in gt:
                rec_codes.add("REC_ADD_FAQ_SECTION")
            if "howto" in gt or "step" in gt:
                rec_codes.add("REC_ADD_HOWTO_OR_STEPS")
            if "heading" in gt or "question" in gt:
                rec_codes.add("REC_ADD_QUESTION_HEADINGS")

    body = _strip_html_only(raw)
    title = _extract_title(body, title_hint or pi.get("title") or brief.get("proposed_title"))

    # Prefer brief proposed H1 when present and current H1 is missing/untitled-ish.
    proposed_h1 = brief.get("proposed_h1") or brief.get("proposed_title")
    if proposed_h1 and title and title.lower() in {"untitled", "(untitled)", "untitled document"}:
        body = _H1_RE.sub(f"# {proposed_h1}", body, count=1)
        title = str(proposed_h1)

    lead = None
    if "REC_ADD_ANSWER_FIRST" in rec_codes:
        lead = (
            brief.get("executive_summary")
            if isinstance(brief.get("executive_summary"), str)
            else None
        )
        if isinstance(brief.get("executive_summary"), dict):
            lead = brief["executive_summary"].get("summary") or brief["executive_summary"].get(
                "text"
            )
        if not lead:
            meta = pi.get("meta_description") or ""
            blocks = pi.get("answer_blocks") or []
            if blocks and isinstance(blocks[0], dict):
                lead = blocks[0].get("text") or blocks[0].get("snippet")
            lead = lead or meta or None
        # Only use lead text that already appears in source (no invented claims).
        if lead and str(lead).strip() and str(lead).strip() not in body:
            # Prefer first paragraph of source after H1 as answer-first reinforcement.
            lead = None
        body = _ensure_answer_first(body, lead if lead else None)
        # If still no answer-first and we have a source opening, leave body unchanged.

    faq_questions: list[str] = []
    for item in brief.get("outline") or []:
        text = item.get("heading") if isinstance(item, dict) else str(item)
        text = str(text or "")
        if "?" in text:
            faq_questions.append(text)
    for h in pi.get("heading_outline") or []:
        if isinstance(h, str) and "?" in h:
            faq_questions.append(h)
    if "REC_ADD_FAQ_SECTION" in rec_codes or "REC_ADD_QUESTION_HEADINGS" in rec_codes:
        if not faq_questions:
            # Use gap rationales as question prompts only when they end with ?
            for g in gap_rows:
                rat = str(g.get("rationale") or "")
                if "?" in rat:
                    faq_questions.append(rat.split("?")[0].strip() + "?")
        body = _ensure_faq_section(body, faq_questions)

    if "REC_ADD_HOWTO_OR_STEPS" in rec_codes:
        body = _ensure_howto_steps(body)

    body = body.strip() + "\n"
    if body.strip() == raw.strip() and not rec_codes and not gap_rows:
        # Still return a labeled copy — current MD is already the best draft.
        labeled = f"{_DISCLAIMER}\n\n{body}"
        return RecommendedMarkdown(
            body=labeled,
            ok=True,
            title=title,
            warnings=["no_material_changes"],
        )

    labeled = f"{_DISCLAIMER}\n\n{body}"
    # Sanity: must remain valid-ish Markdown (fences balanced enough for copy).
    if labeled.count("```") % 2 != 0:
        labeled += "\n```\n"
    return RecommendedMarkdown(
        body=labeled,
        ok=True,
        title=title,
        warnings=[],
    )
