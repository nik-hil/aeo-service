"""Generate paste-ready recommended Markdown for Hashnode workflows.

``RecommendedMarkdown.body`` is ONLY the Markdown a user can paste into Hashnode.
Disclaimers, audit text, instructional placeholders, and HTML-only SEO never
belong in ``body``. Insufficient evidence → skip that transform + record warning.

Applies supported edit ops from the optimization change plan / brief
(retain H1, rewrite introduction / answer-first, meta description as SEO
metadata). Never invents facts; never calls an LLM.
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
_CODE_FENCE_RE = re.compile(r"(^```.*?$.*?^```$)", re.M | re.S)
_DEF_SENTENCE_RE = re.compile(
    r"\b(?:is|are|means|becomes|refers to|consists of)\b",
    re.I,
)
_INVENTED_FACT_RE = re.compile(
    r"\b(?:\d+(?:\.\d+)?%|\d{4}\s+(?:study|report)|according to|"
    r"research shows|studies show|cited? from)\b",
    re.I,
)

GENERATOR_VERSION = "hashnode_recommended_markdown_v1"

# UI metadata only — never written into ``body``.
SUGGESTED_MARKDOWN_SUBTITLE = (
    "Suggested Markdown draft — review before publishing."
)

# Targets the deterministic Markdown generator can apply from change plans.
_SUPPORTED_BODY_TARGETS = frozenset({"h1", "introduction", "intro", "opening", "body"})
_META_TARGETS = frozenset({"meta_description", "seo_description", "seo description"})


@dataclass
class RecommendedMarkdown:
    """Paste-ready Markdown draft plus separate metadata."""

    body: str
    warnings: list[str] = field(default_factory=list)
    changed: bool = False
    source_url: str | None = None
    generator_version: str = GENERATOR_VERSION
    # Hashnode SEO settings — never inserted as HTML <meta> into body.
    seo_description: str | None = None
    meta_description: str | None = None
    applied_ops: list[str] = field(default_factory=list)

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


def _normalize_op(raw: Any) -> dict[str, str] | None:
    """Normalize EditOp / ContentChange / recommendation-ish dicts to a common shape."""
    if not isinstance(raw, dict):
        return None
    action = str(raw.get("action") or "").strip().lower()
    target = str(
        raw.get("target")
        or raw.get("target_locator")
        or raw.get("anchor_locator")
        or ""
    ).strip()
    instruction = str(
        raw.get("instruction") or raw.get("reason") or raw.get("notes") or ""
    ).strip()
    op_id = str(raw.get("op_id") or "").strip()
    code = str(raw.get("code") or "").strip()
    if not action and code:
        # Recommendation codes are handled separately; skip as edit ops.
        return None
    if not action and not target:
        return None
    return {
        "action": action,
        "target": target,
        "instruction": instruction,
        "op_id": op_id or f"{action}:{target}"[:80],
    }


def _collect_edit_ops(
    *,
    brief: dict[str, Any],
    edit_ops: list[dict[str, Any]] | None,
    change_plan: list[dict[str, Any]] | None,
    content_drafts: list[dict[str, Any]] | None,
) -> list[dict[str, str]]:
    """Gather edit ops from explicit args, brief, work_queue, and draft change_plan."""
    raw_items: list[Any] = []
    if edit_ops:
        raw_items.extend(edit_ops)
    if change_plan:
        raw_items.extend(change_plan)
    for key in ("edit_ops", "work_queue", "legacy_edit_ops"):
        for item in brief.get(key) or []:
            raw_items.append(item)
    for draft in content_drafts or []:
        if not isinstance(draft, dict):
            continue
        for item in draft.get("change_plan") or []:
            raw_items.append(item)
        for item in draft.get("edit_ops") or []:
            raw_items.append(item)

    out: list[dict[str, str]] = []
    seen: set[str] = set()
    for raw in raw_items:
        op = _normalize_op(raw)
        if not op:
            continue
        key = f"{op['action']}|{op['target']}|{op['instruction'][:60]}"
        if key in seen:
            continue
        seen.add(key)
        out.append(op)
    return out


def _target_key(target: str) -> str:
    t = (target or "").strip().lower()
    if t.startswith("section:"):
        return "section"
    if t in _META_TARGETS or "meta_description" in t or t.endswith("seo_description"):
        return "meta_description"
    if t in ("h1", "title"):
        return "h1"
    if t in _SUPPORTED_BODY_TARGETS:
        return t
    return t


def _is_retain_h1_op(op: dict[str, str]) -> bool:
    return op.get("action") == "retain" and _target_key(op.get("target") or "") == "h1"


def _is_meta_op(op: dict[str, str]) -> bool:
    return _target_key(op.get("target") or "") == "meta_description" and op.get(
        "action"
    ) in {"add", "expand", "rewrite"}


def _is_intro_rewrite_op(op: dict[str, str], *, h1: str | None) -> bool:
    """True for rewrite/expand ops that target the introduction / H1 section."""
    action = op.get("action") or ""
    if action not in {"rewrite", "expand", "add"}:
        return False
    target = (op.get("target") or "").strip()
    instruction = (op.get("instruction") or "").lower()
    key = _target_key(target)
    if key in {"introduction", "intro", "opening"}:
        return True
    if "answer-first" in instruction or "answer first" in instruction:
        if key in {"section", "introduction", "intro", "opening", "body", "h1"} or (
            target.lower().startswith("section:")
        ):
            return True
    if "introduction" in instruction and action == "rewrite":
        return True
    if target.lower().startswith("section:") and h1:
        section_name = target.split(":", 1)[1].strip()
        if section_name.lower() == h1.lower():
            # Primary H1 section rewrite = introduction (brief convention).
            return True
    return False


def _split_front_matter_safe(md: str) -> tuple[str, list[str], str]:
    """Return (h1_line_or_empty, intro_paragraph_blocks, remainder_including_headings).

    Intro = content after H1 until the first ATX heading. Code fences in the
    intro are kept as atomic blocks so rewrites never split them.
    """
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

    # Group intro into paragraph blocks (blank-line separated), preserving fences.
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


def _score_answer_first_block(text: str) -> float:
    """Higher = better answer-first lead. Only scores existing text."""
    t = (text or "").strip()
    if not t or t.startswith("```") or t.startswith("![") or t.startswith("|"):
        return -1.0
    if t.startswith(">") and len(t) < 40:
        return 0.5
    score = 0.0
    if _DEF_SENTENCE_RE.search(t):
        score += 3.0
    if re.search(r"\b(?:when|because|so that|in order to)\b", t, re.I):
        score += 1.5
    if t.endswith("."):
        score += 0.5
    # Prefer concise declarative leads over long narrative.
    words = len(t.split())
    if 12 <= words <= 60:
        score += 2.0
    elif 8 <= words < 12 or 60 < words <= 90:
        score += 1.0
    elif words < 6:
        score -= 1.0
    # Soft-penalize rhetorical / teaser openers.
    if re.search(
        r"\b(?:sounds?|seems?|appears?)\b.*\b(?:simple|easy|hard|complicated)\b",
        t,
        re.I,
    ):
        score -= 2.0
    if t.endswith("?") and words < 20:
        score -= 1.5
    return score


def _answer_first_lead_from_evidence(
    intro_blocks: list[str],
    *,
    body: str,
    pi: dict[str, Any],
    brief: dict[str, Any],
) -> str | None:
    """Pick an answer-first lead using only text already present on the page.

    Does **not** invent facts. Does **not** use diagnostic executive_summary.
    Does **not** use meta_description alone (decoupled from meta ops).
    """
    candidates: list[tuple[float, str]] = []

    for block in intro_blocks:
        if block.startswith("```"):
            continue
        # Prefer whole paragraphs; also consider individual sentences.
        score = _score_answer_first_block(block)
        if score >= 0:
            candidates.append((score, block.strip()))
        for sent in re.split(r"(?<=[.!?])\s+", block.strip()):
            sent = sent.strip()
            if len(sent.split()) < 8:
                continue
            s_score = _score_answer_first_block(sent)
            if s_score > score:
                candidates.append((s_score, sent))

    # Page-intelligence answer blocks — only if the snippet already appears in body.
    for block in pi.get("answer_blocks") or []:
        if not isinstance(block, dict):
            continue
        snippet = str(block.get("snippet") or block.get("text") or "").strip()
        if not snippet or len(snippet) < 24:
            continue
        if snippet not in (body or "") and snippet not in "\n".join(intro_blocks):
            continue
        candidates.append((_score_answer_first_block(snippet) + 0.5, snippet))

    # Meta description only when its text is already grounded in the article body
    # (not merely missing-meta). Used as answerability evidence, not meta op.
    meta = str(pi.get("meta_description") or brief.get("proposed_meta_description") or "").strip()
    if meta and meta in (body or ""):
        candidates.append((_score_answer_first_block(meta) + 0.25, meta))

    if not candidates:
        return None
    candidates.sort(key=lambda x: (-x[0], len(x[1])))
    best_score, best = candidates[0]
    if best_score < 1.0:
        return None
    if _INVENTED_FACT_RE.search(best) and best not in (body or "") and best not in "\n".join(
        intro_blocks
    ):
        return None
    return best.strip()


def _rewrite_introduction_answer_first(
    md: str, lead: str | None
) -> tuple[str, bool]:
    """Reorder / insert answer-first lead in the intro; preserve the rest of the doc."""
    if not lead or not lead.strip():
        return md, False
    lead = lead.strip()
    h1_line, intro_blocks, remainder = _split_front_matter_safe(md)
    if not h1_line:
        return md, False

    # Idempotent: already answer-first with this lead.
    if intro_blocks and intro_blocks[0].strip() == lead:
        return md, False

    # Remove lead from later intro blocks if it was moved from within intro.
    remaining: list[str] = []
    for block in intro_blocks:
        if block.strip() == lead:
            continue
        # If lead is a sentence carved from a paragraph, drop that exact sentence.
        if lead in block and not block.startswith("```"):
            trimmed = block.replace(lead, "", 1).strip()
            trimmed = re.sub(r"\s{2,}", " ", trimmed).strip()
            if trimmed:
                remaining.append(trimmed)
            continue
        remaining.append(block)

    new_intro = [lead] + remaining
    parts = [h1_line, ""]
    for block in new_intro:
        parts.append(block)
        parts.append("")
    if remainder.strip():
        # Avoid double blank before next heading.
        parts.append(remainder.lstrip("\n"))
    else:
        # Keep trailing newline consistency.
        pass
    out = "\n".join(parts).rstrip() + "\n"
    return out, out.strip() != (md or "").strip()


def _ensure_answer_first(md: str, lead: str | None) -> tuple[str, bool]:
    """Backward-compatible wrapper: rewrite intro to answer-first when evidence exists."""
    return _rewrite_introduction_answer_first(md, lead)


def _existing_faq_qa_pairs(md: str) -> list[tuple[str, str]]:
    """Collect question headings that already have following answer paragraphs.

    Skips fenced code blocks so code comments / prompts are not treated as Q&A.
    """
    lines = (md or "").splitlines()
    pairs: list[tuple[str, str]] = []
    i = 0
    in_fence = False
    while i < len(lines):
        if lines[i].strip().startswith("```"):
            in_fence = not in_fence
            i += 1
            continue
        if in_fence:
            i += 1
            continue
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
            if lines[j].strip().startswith("```"):
                break
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
    """Legacy helper — answerability evidence only (not meta-only, not exec summary)."""
    blocks = pi.get("answer_blocks") or []
    if blocks and isinstance(blocks[0], dict):
        lead = blocks[0].get("text") or blocks[0].get("snippet")
        if lead and str(lead).strip():
            return str(lead).strip()
    return None


def _resolve_seo_description(
    *,
    brief: dict[str, Any],
    pi: dict[str, Any],
    body: str,
) -> str | None:
    """Build Hashnode SEO description from existing page/brief evidence only."""
    proposed = brief.get("proposed_meta_description")
    if isinstance(proposed, str) and proposed.strip():
        text = proposed.strip()
    else:
        existing = str(pi.get("meta_description") or "").strip()
        if existing:
            text = existing
        else:
            # Fall back to first intro paragraph already in the Markdown body.
            _, intro_blocks, _ = _split_front_matter_safe(body)
            text = ""
            for block in intro_blocks:
                if block.startswith("```"):
                    continue
                cand = block.strip()
                if 40 <= len(cand) <= 200:
                    text = cand
                    break
            if not text:
                return None
    # Strip HTML; keep plain text for Hashnode SEO settings field.
    text = _HTML_TAG_RE.sub("", text).strip()
    text = re.sub(r"\s+", " ", text)
    if len(text) > 160:
        text = text[:157].rstrip() + "…"
    if not text or _INVENTED_FACT_RE.search(text) and text not in body and text not in str(
        pi.get("meta_description") or ""
    ):
        # Allow known existing meta even if it matches the pattern; block novel claims.
        if text not in str(pi.get("meta_description") or "") and text not in str(
            brief.get("proposed_meta_description") or ""
        ):
            return None
    return text


def _wants_answer_first(
    *,
    ops: list[dict[str, str]],
    rec_codes: set[str],
    h1: str | None,
    pi: dict[str, Any],
) -> tuple[bool, bool]:
    """Return (should_rewrite_intro, driven_by_meta_only).

    Meta-description ops alone must NOT drive intro rewrite.
    """
    has_intro_op = any(_is_intro_rewrite_op(op, h1=h1) for op in ops)
    has_meta_op = any(_is_meta_op(op) for op in ops)
    has_answer_rec = "REC_ADD_ANSWER_FIRST" in rec_codes
    ans = pi.get("answerability_signals") or pi.get("answerability") or {}
    no_answer_first = False
    if isinstance(ans, dict):
        if ans.get("answer_first_heuristic") is False:
            no_answer_first = True
    limits = pi.get("limits") or []
    if "no_answer_first" in limits:
        no_answer_first = True

    if has_intro_op or has_answer_rec or no_answer_first:
        return True, False
    if has_meta_op and not (has_intro_op or has_answer_rec or no_answer_first):
        return False, True
    return False, False


def generate_recommended_markdown(
    *,
    source_markdown: str | None,
    page_intelligence: dict[str, Any] | None = None,
    brief: dict[str, Any] | None = None,
    gaps: list[dict[str, Any]] | None = None,
    recommendations: list[dict[str, Any]] | None = None,
    edit_ops: list[dict[str, Any]] | None = None,
    change_plan: list[dict[str, Any]] | None = None,
    content_drafts: list[dict[str, Any]] | None = None,
    title_hint: str | None = None,
    source_url: str | None = None,
) -> RecommendedMarkdown:
    """Build paste-ready Markdown from current MD + evidence-backed edit ops only.

    Never fabricates product facts; never puts disclaimers or instructional
    placeholders in ``body``. UI shows honesty labeling as metadata/subtitle.
    Meta description ops are applied as ``seo_description`` metadata, not body HTML.
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
    applied_ops: list[str] = []
    seo_description: str | None = None

    ops = _collect_edit_ops(
        brief=brief,
        edit_ops=edit_ops,
        change_plan=change_plan,
        content_drafts=content_drafts,
    )

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
    h1 = title or (str(pi.get("h1")).strip() if pi.get("h1") else None)

    # --- retain H1 (explicit no-op on body; records application) ---
    retain_ops = [op for op in ops if _is_retain_h1_op(op)]
    if retain_ops and h1:
        applied_ops.append(retain_ops[0]["op_id"] or "retain:h1")
    elif retain_ops and not h1:
        warnings.append("retain_h1_skipped_missing_h1")

    # Untitled placeholder → allow proposed H1 only when source H1 is placeholder.
    proposed_h1 = brief.get("proposed_h1") or brief.get("proposed_title")
    if proposed_h1 and title and title.lower() in {
        "untitled",
        "(untitled)",
        "untitled document",
    }:
        body = _H1_RE.sub(f"# {proposed_h1}", body, count=1)
        title = str(proposed_h1)
        h1 = title
        applied_ops.append("replace_placeholder_h1")

    # --- meta description → SEO metadata (never HTML <meta> in body) ---
    meta_ops = [op for op in ops if _is_meta_op(op)]
    # Also honor REC_ADD_META_DESCRIPTION as a metadata-only signal.
    if "REC_ADD_META_DESCRIPTION" in rec_codes and not meta_ops:
        meta_ops = [
            {
                "action": "add",
                "target": "meta_description",
                "instruction": "Add SEO description",
                "op_id": "rec_add_meta_description",
            }
        ]
    if meta_ops:
        seo = _resolve_seo_description(brief=brief, pi=pi, body=body)
        if seo:
            seo_description = seo
            applied_ops.append(meta_ops[0]["op_id"] or "meta_description")
            warnings.append("seo_description_for_hashnode_settings")
        else:
            warnings.append("insufficient_evidence_meta_description")

    # --- introduction / answer-first (body) ---
    wants_intro, meta_only_drive = _wants_answer_first(
        ops=ops, rec_codes=rec_codes, h1=h1, pi=pi
    )
    if meta_only_drive:
        warnings.append("meta_description_does_not_drive_intro_rewrite")

    body_op_applied = False
    if wants_intro:
        _, intro_blocks, _ = _split_front_matter_safe(body)
        lead = _answer_first_lead_from_evidence(
            intro_blocks, body=body, pi=pi, brief=brief
        )
        if not lead:
            # Fallback: legacy answer-block lead only if already in body.
            legacy = _lead_from_brief_or_pi(brief, pi)
            if legacy and legacy in body:
                lead = legacy
        body, did = _rewrite_introduction_answer_first(body, lead)
        if did:
            body_op_applied = True
            intro_op = next(
                (op for op in ops if _is_intro_rewrite_op(op, h1=h1)),
                None,
            )
            applied_ops.append(
                (intro_op or {}).get("op_id")
                or "rewrite:introduction_answer_first"
            )
        else:
            warnings.append("insufficient_evidence_answer_first")

    # --- FAQ / HowTo (evidence-backed only; existing behavior) ---
    if "REC_ADD_FAQ_SECTION" in rec_codes or "REC_ADD_QUESTION_HEADINGS" in rec_codes:
        qa_pairs = _existing_faq_qa_pairs(body)
        if not qa_pairs:
            for item in brief.get("outline") or []:
                text = item.get("heading") if isinstance(item, dict) else str(item)
                text = str(text or "").strip()
                if "?" not in text:
                    continue
                if text in body:
                    pass
            qa_pairs = _existing_faq_qa_pairs(body)
        body, did = _ensure_faq_section(body, qa_pairs)
        if did:
            body_op_applied = True
            applied_ops.append("add:faq_section")
        else:
            warnings.append("insufficient_evidence_faq")

    if "REC_ADD_HOWTO_OR_STEPS" in rec_codes:
        steps = _extract_numbered_steps(body)
        if len(steps) < 3:
            for m in re.finditer(
                r"^Step\s+\d+\s*[:.\-]\s*(.+)$", body or "", re.I | re.M
            ):
                steps.append(m.group(1).strip())
        body, did = _ensure_howto_steps(body, steps)
        if did:
            body_op_applied = True
            applied_ops.append("add:howto_steps")
        else:
            warnings.append("insufficient_evidence_howto")

    # Unsupported actionable ops → warn, leave body alone for those targets.
    for op in ops:
        if _is_retain_h1_op(op) or _is_meta_op(op) or _is_intro_rewrite_op(op, h1=h1):
            continue
        action = op.get("action") or ""
        target = (op.get("target") or "").strip()
        key = _target_key(target)
        t_lower = target.lower()
        # Known non-body / unsupported for Hashnode MD generator.
        if (
            key in {"cross_page_link", "body"}
            or t_lower.startswith("schema:")
            or t_lower.startswith("internal_link")
            or key == "section"
            or t_lower.startswith("section:")
        ):
            warnings.append(
                f"unsupported_edit_op:{action}:{key if key != 'section' else t_lower}"
            )

    body = body.strip() + "\n"
    cleaned_source = (_strip_html_only(raw)).strip() + "\n"
    cleaned_source = _strip_instructional_placeholders(cleaned_source).strip() + "\n"
    # changed reflects Markdown **body** only — metadata-only ⇒ False.
    changed = body.strip() != cleaned_source.strip()

    # Invariant: at least one supported actionable *content* op applied ⇒ changed.
    if body_op_applied and not changed:
        warnings.append("invariant_body_op_without_change")

    if not changed and not rec_codes and not gap_rows and not ops:
        warnings = list(dict.fromkeys(warnings + ["no_material_changes"]))
    elif not changed and ops and not body_op_applied:
        if meta_ops and seo_description and not wants_intro:
            warnings = list(
                dict.fromkeys(warnings + ["metadata_only_no_body_change"])
            )
        elif not any(
            _is_intro_rewrite_op(op, h1=h1)
            or "REC_ADD_ANSWER_FIRST" in rec_codes
            for op in ops
        ):
            warnings = list(
                dict.fromkeys(warnings + ["no_supported_body_ops_applied"])
            )

    warnings = list(dict.fromkeys(warnings))
    applied_ops = list(dict.fromkeys(applied_ops))

    return RecommendedMarkdown(
        body=body,
        warnings=warnings,
        changed=changed,
        source_url=resolved_source_url,
        seo_description=seo_description,
        meta_description=seo_description,
        applied_ops=applied_ops,
    )
