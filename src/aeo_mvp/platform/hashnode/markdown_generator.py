"""Generate paste-ready recommended Markdown for Hashnode workflows.

``RecommendedMarkdown.body`` is ONLY the Markdown a user can paste into Hashnode.
Disclaimers, audit text, instructional placeholders, and HTML-only SEO never
belong in ``body``. Insufficient evidence → skip that transform + record warning.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

_H1_RE = re.compile(r"^#\s+(.+)$", re.MULTILINE)
_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+)$", re.MULTILINE)
_HTML_TAG_RE = re.compile(
    r"</?(?:script|style|meta|link|html|head|body)[^>]*>", re.I
)
_JSONLD_FENCE_RE = re.compile(
    r"```(?:json|jsonld)?\s*\{[^{}]*\"@context\"[^{}]*\}```",
    re.I | re.S,
)
_INSTRUCTIONAL_PLACEHOLDER_RE = re.compile(
    r"^_Add a concise,.*?_$\n?"
    r"|^_Describe the (?:first concrete|next|final verification) step.*?_$\n?",
    re.I | re.M,
)
_LEGACY_DISCLAIMER_RE = re.compile(
    r"^\s*\*{0,2}RECOMMENDED MARKDOWN\*{0,2}[^\n]*\n+"
    r"(?:[^\n]*not a final[^\n]*\n+)?(?:---\n+)?",
    re.I,
)

GENERATOR_VERSION = "hashnode_recommended_markdown_v1"

# UI metadata only — never written into ``body``.
SUGGESTED_MARKDOWN_SUBTITLE = (
    "Suggested Markdown draft — review before publishing."
)


@dataclass
class RecommendedMarkdown:
    """Paste-ready Markdown draft plus separate metadata."""

    body: str
    warnings: list[str] = field(default_factory=list)
    changed: bool = False
    source_url: str | None = None
    generator_version: str = GENERATOR_VERSION

    @property
    def ok(self) -> bool:
        return bool((self.body or "").strip())

    @property
    def generator(self) -> str:
        return self.generator_version

    @property
    def title(self) -> str | None:
        return _extract_title(self.body)


def _strip_html_only(text: str) -> str:
    """Remove HTML-only constructs authors cannot control in Hashnode Markdown."""
    out = _HTML_TAG_RE.sub("", text or "")
    out = _JSONLD_FENCE_RE.sub("", out)
    return out


def _strip_instructional_placeholders(text: str) -> str:
    return _INSTRUCTIONAL_PLACEHOLDER_RE.sub("", text or "")


def strip_legacy_recommended_chrome(text: str) -> str:
    """Remove legacy disclaimer / RECOMMENDED MARKDOWN heading from stored drafts."""
    out = (text or "").strip()
    out = _LEGACY_DISCLAIMER_RE.sub("", out, count=1)
    # Drop a lone leading "# RECOMMENDED MARKDOWN" heading if present.
    out = re.sub(
        r"^#\s*RECOMMENDED MARKDOWN\s*\n+(?:Status:[^\n]*\n+)?(?:_[^_]+_\n+)?(?:---\n+)?",
        "",
        out,
        count=1,
        flags=re.I,
    )
    return out.strip()


def _extract_title(md: str, fallback: str | None = None) -> str | None:
    m = _H1_RE.search(md or "")
    if m:
        return m.group(1).strip()[:200] or fallback
    return fallback


def _ensure_answer_first(md: str, lead: str | None) -> tuple[str, bool]:
    """Insert answer-first lead only when the text already appears in the source."""
    if not lead or not lead.strip():
        return md, False
    lead = lead.strip()
    if lead not in (md or ""):
        return md, False
    lines = (md or "").splitlines()
    if not lines:
        return md, False
    idx = next((i for i, ln in enumerate(lines) if ln.startswith("# ")), None)
    if idx is None:
        return md, False
    j = idx + 1
    while j < len(lines) and not lines[j].strip():
        j += 1
    if j < len(lines) and not lines[j].startswith("#"):
        return md, False
    insert = ["", lead, ""]
    return "\n".join(lines[: idx + 1] + insert + lines[idx + 1 :]), True


def _existing_faq_qa_pairs(md: str) -> list[tuple[str, str]]:
    """Collect question headings that already have following answer paragraphs."""
    lines = (md or "").splitlines()
    pairs: list[tuple[str, str]] = []
    i = 0
    while i < len(lines):
        m = re.match(r"^(#{2,6})\s+(.+\?)\s*$", lines[i])
        if not m:
            i += 1
            continue
        question = m.group(2).strip()
        j = i + 1
        while j < len(lines) and not lines[j].strip():
            j += 1
        answer_parts: list[str] = []
        while j < len(lines) and lines[j].strip() and not lines[j].startswith("#"):
            answer_parts.append(lines[j].strip())
            j += 1
        answer = " ".join(answer_parts).strip()
        if answer and not answer.startswith("_") and "invent" not in answer.lower():
            pairs.append((question, answer))
        i = j if j > i else i + 1
    return pairs


def _ensure_faq_section(md: str, qa_pairs: list[tuple[str, str]]) -> tuple[str, bool]:
    """Add an FAQ section only when evidence-backed Q&A pairs exist."""
    if not qa_pairs:
        return md, False
    lower = (md or "").lower()
    if "faq" in lower or "frequently asked" in lower:
        return md, False
    parts = [md.rstrip(), "", "## FAQ", ""]
    for q, a in qa_pairs[:5]:
        parts.append(f"### {q}")
        parts.append("")
        parts.append(a)
        parts.append("")
    return "\n".join(parts).rstrip() + "\n", True


def _extract_numbered_steps(md: str) -> list[str]:
    steps: list[str] = []
    for m in re.finditer(r"^\d+\.\s+(.+)$", md or "", re.M):
        text = m.group(1).strip()
        if text.startswith("_") and text.endswith("_"):
            continue
        if text:
            steps.append(text)
    return steps


def _ensure_howto_steps(md: str, steps: list[str]) -> tuple[str, bool]:
    """Promote evidence-backed numbered steps; never invent placeholder steps."""
    if len(steps) < 3:
        return md, False
    lower = (md or "").lower()
    if "step-by-step" in lower or re.search(r"^##\s+steps\b", md or "", re.I | re.M):
        return md, False
    # Already has a full numbered list in-body — leave unchanged.
    if len(_extract_numbered_steps(md)) >= 3:
        return md, False
    parts = [md.rstrip(), "", "## Steps", ""]
    for i, step in enumerate(steps[:8], start=1):
        parts.append(f"{i}. {step}")
    parts.append("")
    return "\n".join(parts), True


def _lead_from_brief_or_pi(
    brief: dict[str, Any], pi: dict[str, Any]
) -> str | None:
    lead = None
    if isinstance(brief.get("executive_summary"), str):
        lead = brief.get("executive_summary")
    elif isinstance(brief.get("executive_summary"), dict):
        lead = brief["executive_summary"].get("summary") or brief[
            "executive_summary"
        ].get("text")
    if not lead:
        meta = pi.get("meta_description") or ""
        blocks = pi.get("answer_blocks") or []
        if blocks and isinstance(blocks[0], dict):
            lead = blocks[0].get("text") or blocks[0].get("snippet")
        lead = lead or meta or None
    return str(lead).strip() if lead else None


def generate_recommended_markdown(
    *,
    source_markdown: str | None,
    page_intelligence: dict[str, Any] | None = None,
    brief: dict[str, Any] | None = None,
    gaps: list[dict[str, Any]] | None = None,
    recommendations: list[dict[str, Any]] | None = None,
    title_hint: str | None = None,
    source_url: str | None = None,
) -> RecommendedMarkdown:
    """Build paste-ready Markdown from current MD + evidence-backed edits only.

    Never fabricates product facts; never puts disclaimers or instructional
    placeholders in ``body``. UI shows honesty labeling as metadata/subtitle.
    """
    pi = page_intelligence or {}
    resolved_source_url = source_url or pi.get("source_url") or pi.get("url")
    raw = strip_legacy_recommended_chrome((source_markdown or "").strip())
    if not raw:
        return RecommendedMarkdown(
            body="",
            warnings=["no_source_markdown"],
            changed=False,
            source_url=resolved_source_url,
        )

    brief = brief or {}
    gap_rows = list(gaps or [])
    warnings: list[str] = []
    rec_codes = {
        str(r.get("code") or "")
        for r in (recommendations or [])
        if isinstance(r, dict)
    }
    for g in gap_rows:
        if isinstance(g, dict) and g.get("gap_type"):
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
    body = _strip_instructional_placeholders(body)
    title = _extract_title(
        body, title_hint or pi.get("title") or brief.get("proposed_title")
    )

    proposed_h1 = brief.get("proposed_h1") or brief.get("proposed_title")
    if proposed_h1 and title and title.lower() in {
        "untitled",
        "(untitled)",
        "untitled document",
    }:
        body = _H1_RE.sub(f"# {proposed_h1}", body, count=1)
        title = str(proposed_h1)

    if "REC_ADD_ANSWER_FIRST" in rec_codes:
        lead = _lead_from_brief_or_pi(brief, pi)
        body, did = _ensure_answer_first(body, lead)
        if not did:
            warnings.append("insufficient_evidence_answer_first")

    if "REC_ADD_FAQ_SECTION" in rec_codes or "REC_ADD_QUESTION_HEADINGS" in rec_codes:
        qa_pairs = _existing_faq_qa_pairs(body)
        # Prefer outline questions only when the question text already exists in body
        # and we can pair it with a following non-placeholder paragraph.
        if not qa_pairs:
            for item in brief.get("outline") or []:
                text = item.get("heading") if isinstance(item, dict) else str(item)
                text = str(text or "").strip()
                if "?" not in text:
                    continue
                if text in body:
                    # Find answer text after that occurrence if structured as heading.
                    pass
            qa_pairs = _existing_faq_qa_pairs(body)
        body, did = _ensure_faq_section(body, qa_pairs)
        if not did:
            warnings.append("insufficient_evidence_faq")

    if "REC_ADD_HOWTO_OR_STEPS" in rec_codes:
        steps = _extract_numbered_steps(body)
        # Also accept explicit "Step N:" lines as evidence.
        if len(steps) < 3:
            for m in re.finditer(
                r"^Step\s+\d+\s*[:.\-]\s*(.+)$", body or "", re.I | re.M
            ):
                steps.append(m.group(1).strip())
        body, did = _ensure_howto_steps(body, steps)
        if not did:
            warnings.append("insufficient_evidence_howto")

    body = body.strip() + "\n"
    cleaned_source = (_strip_html_only(raw)).strip() + "\n"
    cleaned_source = _strip_instructional_placeholders(cleaned_source).strip() + "\n"
    changed = body.strip() != cleaned_source.strip()

    if not changed and not rec_codes and not gap_rows:
        warnings = list(dict.fromkeys(warnings + ["no_material_changes"]))

    # Drop duplicate warnings while preserving order.
    warnings = list(dict.fromkeys(warnings))

    return RecommendedMarkdown(
        body=body,
        warnings=warnings,
        changed=changed,
        source_url=resolved_source_url,
    )
