"""Generate paste-ready recommended Markdown for Hashnode workflows.

``RecommendedMarkdown.body`` is ONLY the Markdown a user can paste into Hashnode.
Disclaimers, audit text, instructional placeholders, and HTML-only SEO never
belong in ``body``. Insufficient evidence → skip that transform + record warning.

Applies supported edit ops from the optimization change plan / brief
(retain H1, introduction rewrite via validated ``proposed``, meta description
as SEO metadata). Never invents facts; never calls an LLM.

Intro / ``rewrite`` semantics (deterministic mode)
-------------------------------------------------
The change-plan edit-op contract may name the action ``rewrite`` (e.g.
``rewrite`` + ``section:<H1>`` / ``introduction`` with an answer-first
instruction). This generator does **not** invent rewrite copy and must
**not** call ``propose_introduction_rewrite`` /
``enrich_ops_with_rewrite_proposals``. The content optimization layer
produces a validated ``proposed`` replacement (with ``original`` /
``evidence`` / ``reason`` / ``related_gap_ids``) before handoff. This
generator defensively re-validates, then **applies** that proposal to the
correct Markdown region — or skips and leaves the original unchanged when
``proposed`` is absent/invalid.

A bare paragraph move / reorder without ``proposed`` is **not** treated as a
successful content rewrite. No proposal ⇒ no rewrite.

Meta / SEO description provenance
---------------------------------
``brief.proposed_meta_description`` is owned by the upstream optimization
brief (generation + provenance live there). This Hashnode MD generator only
**transports** that value (or observed page-intel meta) as separate
``seo_description`` / ``meta_description`` metadata for Hashnode SEO
settings. It does **not** claim the text was derived from source Markdown,
and never inserts HTML ``<meta>`` into the Markdown body. Metadata-only
application leaves ``changed=False``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from aeo_mvp.content.rewrite_proposal import validate_proposed_rewrite

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
    # Hashnode SEO settings transport only — never HTML <meta> in body.
    # Value may come from brief.proposed_meta_description (upstream) or
    # observed page intel; see module docstring for provenance boundary.
    seo_description: str | None = None
    meta_description: str | None = None
    applied_ops: list[str] = field(default_factory=list)
    # Explicit rewrite provenance for UI / report (never injected into body).
    rewrite_provenance: dict[str, Any] | None = None

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


def _normalize_op(raw: Any) -> dict[str, Any] | None:
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
    evidence_raw = raw.get("evidence") or raw.get("must_cite_locators") or []
    evidence: list[str] = []
    if isinstance(evidence_raw, list):
        evidence = [str(e).strip() for e in evidence_raw if str(e).strip()]
    related = raw.get("related_gap_ids") or []
    related_gap_ids = (
        [str(g) for g in related if str(g).strip()] if isinstance(related, list) else []
    )
    original = raw.get("original")
    proposed = raw.get("proposed")
    op_kind = str(raw.get("op_kind") or "").strip() or None
    disposition = str(raw.get("disposition") or "").strip() or None
    expected_aeo_benefit = str(raw.get("expected_aeo_benefit") or "").strip()
    apply_mode = str(raw.get("apply_mode") or "").strip() or None
    status = str(raw.get("status") or "").strip() or None
    target_kind = str(raw.get("target_kind") or "").strip() or None
    return {
        "action": action,
        "target": target,
        "instruction": instruction,
        "op_id": op_id or f"{action}:{target}"[:80],
        "original": str(original).strip() if isinstance(original, str) else "",
        "proposed": str(proposed).strip() if isinstance(proposed, str) else "",
        "evidence": evidence,
        "related_gap_ids": related_gap_ids,
        "op_kind": op_kind,
        "disposition": disposition,
        "expected_aeo_benefit": expected_aeo_benefit,
        "apply_mode": apply_mode,
        "status": status,
        "target_kind": target_kind,
    }


def _collect_edit_ops(
    *,
    brief: dict[str, Any],
    edit_ops: list[dict[str, Any]] | None,
    change_plan: list[dict[str, Any]] | None,
    content_drafts: list[dict[str, Any]] | None,
) -> list[dict[str, Any]]:
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

    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for raw in raw_items:
        op = _normalize_op(raw)
        if not op:
            continue
        key = (
            f"{op['action']}|{op['target']}|{op['instruction'][:60]}|"
            f"{(op.get('proposed') or '')[:40]}"
        )
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


def _is_retain_h1_op(op: dict[str, Any]) -> bool:
    return op.get("action") == "retain" and _target_key(op.get("target") or "") == "h1"


def _is_meta_op(op: dict[str, Any]) -> bool:
    return _target_key(op.get("target") or "") == "meta_description" and op.get(
        "action"
    ) in {"add", "expand", "rewrite"}


def _is_intro_rewrite_op(op: dict[str, Any], *, h1: str | None) -> bool:
    """True when the change-plan op targets introduction / answer-first."""
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
            # Primary H1 section → introduction (brief convention).
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


def _apply_proposed_introduction(
    md: str, proposed: str
) -> tuple[str, bool]:
    """Replace intro region (after H1, before next heading) with validated proposed.

    Preserves H1 and all post-intro headings / body. Does not invent content.
    """
    proposed = (proposed or "").strip()
    if not proposed:
        return md, False
    h1_line, intro_blocks, remainder = _split_front_matter_safe(md)
    if not h1_line:
        return md, False

    current_intro = "\n\n".join(intro_blocks).strip()
    # Idempotent: proposed already applied.
    if current_intro == proposed:
        return md, False

    parts = [h1_line, "", proposed, ""]
    if remainder.strip():
        parts.append(remainder.lstrip("\n"))
    out = "\n".join(parts).rstrip() + "\n"
    return out, out.strip() != (md or "").strip()


def _find_section_span(
    md: str, heading: str
) -> tuple[int, int, int, str] | None:
    """Return (heading_line_idx, body_start_idx, body_end_idx, heading_line).

    body spans lines after the heading until the next same-or-higher-level
    ATX heading (or EOF). Indices are into splitlines().
    """
    lines = (md or "").splitlines()
    want = (heading or "").strip().lower()
    if not want:
        return None
    in_fence = False
    for i, ln in enumerate(lines):
        if ln.strip().startswith("```"):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        m = re.match(r"^(#{1,6})\s+(.+)$", ln)
        if not m:
            continue
        title = m.group(2).strip()
        if title.lower() != want and want not in title.lower():
            continue
        level = len(m.group(1))
        body_start = i + 1
        body_end = len(lines)
        j = body_start
        in_fence2 = False
        while j < len(lines):
            if lines[j].strip().startswith("```"):
                in_fence2 = not in_fence2
                j += 1
                continue
            if not in_fence2:
                m2 = re.match(r"^(#{1,6})\s+", lines[j])
                if m2 and len(m2.group(1)) <= level:
                    body_end = j
                    break
            j += 1
        return i, body_start, body_end, ln
    return None


def _apply_proposed_section_rewrite(
    md: str, heading: str, proposed: str
) -> tuple[str, bool]:
    """Replace a section body (not the heading line) with validated proposed."""
    proposed = (proposed or "").strip()
    if not proposed or not heading:
        return md, False
    span = _find_section_span(md, heading)
    if span is None:
        return md, False
    _h_idx, body_start, body_end, heading_line = span
    lines = (md or "").splitlines()
    current = "\n".join(lines[body_start:body_end]).strip("\n")
    if current.strip() == proposed:
        return md, False
    new_body_lines = proposed.splitlines()
    out_lines = lines[:body_start] + new_body_lines
    # Preserve a blank line before the next heading when present.
    rest = lines[body_end:]
    if rest and new_body_lines and new_body_lines[-1].strip():
        if rest[0].strip():
            out_lines.append("")
    out_lines.extend(rest)
    # Ensure heading line survived.
    if heading_line not in out_lines:
        return md, False
    out = "\n".join(out_lines).rstrip() + "\n"
    return out, out.strip() != (md or "").strip()


def _apply_insert_after_heading(
    md: str, heading: str, proposed: str
) -> tuple[str, bool]:
    """Insert proposed paragraph immediately after a heading (idempotent)."""
    proposed = (proposed or "").strip()
    if not proposed or not heading:
        return md, False
    span = _find_section_span(md, heading)
    if span is None:
        return md, False
    _h_idx, body_start, body_end, _heading_line = span
    lines = (md or "").splitlines()
    # Skip existing blank lines after heading.
    insert_at = body_start
    while insert_at < len(lines) and not lines[insert_at].strip():
        insert_at += 1
    # Idempotent only when the section *lead* already starts with proposed.
    # Buried later occurrences (e.g. a blockquote mid-section) still warrant
    # promotion to the answer-first lead position.
    section_lead = "\n".join(lines[insert_at:body_end]).lstrip()
    if section_lead.startswith(proposed):
        return md, False
    # Also treat blockquote-prefixed lead as already present.
    if section_lead.lstrip("> ").startswith(proposed):
        return md, False
    block_lines = proposed.splitlines()
    out_lines = lines[:body_start]
    if out_lines and out_lines[-1].strip():
        # heading line then blank then proposed
        out_lines.append("")
    out_lines.extend(block_lines)
    out_lines.append("")
    out_lines.extend(lines[insert_at:])
    out = "\n".join(out_lines).rstrip() + "\n"
    return out, out.strip() != (md or "").strip()


def _section_heading_from_target(target: str) -> str | None:
    t = (target or "").strip()
    if t.lower().startswith("section:"):
        return t.split(":", 1)[1].strip() or None
    return None


def _is_ready_mvp_body_op(op: dict[str, Any], *, h1: str | None) -> bool:
    """True for MVP ready body ops the generator may apply (not invent)."""
    status = str(op.get("status") or "").strip()
    apply_mode = str(op.get("apply_mode") or "").strip()
    disposition = str(op.get("disposition") or "").strip()
    if status == "needs_author_input" or apply_mode == "author_input_required":
        return False
    if disposition == "author_input_required":
        return False
    if status and status not in {"ready", ""}:
        # unsupported / deferred → never apply
        if status in {"unsupported", "needs_author_input"}:
            return False
    if apply_mode in {"unsupported", "author_input_required", "metadata_only"}:
        return False
    op_kind = str(op.get("op_kind") or "")
    if op_kind in {
        "_substantive_change_plan",
        "author_input_required",
        "rewrite_section",
        "add_definition",
        "add_answer_first",
        "add_process_summary",
        "clarify_relationship",
        "expand_concept",
        "strengthen_example",
        "improve_conclusion",
        "improve_terminology",
    }:
        return False
    if _is_intro_rewrite_op(op, h1=h1):
        return False
    proposed = op.get("proposed")
    if not isinstance(proposed, str) or not proposed.strip():
        return False
    # FAQ / HowTo promote-only kinds
    if op_kind in {"add_faq_from_existing_qa", "add_howto_from_existing_steps"}:
        return status in {"ready", ""} or disposition == "actionable"
    return False


def _apply_append_block(md: str, proposed: str) -> tuple[str, bool]:
    """Append a proposed block to the end of the document (idempotent)."""
    proposed = (proposed or "").strip()
    if not proposed:
        return md, False
    if proposed in (md or ""):
        return md, False
    out = (md or "").rstrip() + "\n\n" + proposed.strip() + "\n"
    return out, True


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
    """Add an FAQ section only when ≥FAQ_MIN existing evidence-backed Q&A pairs.

    Kept as a helper; ``generate_recommended_markdown`` must not call this from
    legacy REC codes — only ready ``add_faq_from_existing_qa`` ops apply FAQ.
    """
    from aeo_mvp.content.models import FAQ_MIN_EXISTING_QA_PAIRS

    if len(qa_pairs) < FAQ_MIN_EXISTING_QA_PAIRS:
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
    """Promote evidence-backed numbered steps; never invent placeholder steps.

    Requires ≥HOWTO_MIN_EXISTING_STEPS. Not invoked from legacy REC paths.
    """
    from aeo_mvp.content.models import HOWTO_MIN_EXISTING_STEPS

    if len(steps) < HOWTO_MIN_EXISTING_STEPS:
        return md, False
    lower = (md or "").lower()
    if "step-by-step" in lower or re.search(r"^##\s+steps\b", md or "", re.I | re.M):
        return md, False
    # Already has a full numbered list in-body — leave unchanged.
    if len(_extract_numbered_steps(md)) >= HOWTO_MIN_EXISTING_STEPS:
        return md, False
    parts = [md.rstrip(), "", "## Steps", ""]
    for i, step in enumerate(steps[:8], start=1):
        parts.append(f"{i}. {step}")
    parts.append("")
    return "\n".join(parts), True


def _resolve_seo_description(
    *,
    brief: dict[str, Any],
    pi: dict[str, Any],
    body: str,
) -> tuple[str | None, str | None]:
    """Transport Hashnode SEO description into metadata (never into MD body).

    Provenance boundary:
    - Optimization brief owns generation of ``proposed_meta_description``.
      This function only copies it when present; it does **not** assert the
      text was derived from source Markdown.
    - Else observed ``page_intelligence.meta_description`` may be transported.
    - Else, as a last resort, the first suitable intro paragraph already in
      the Markdown body (explicitly source-derived fallback only).
    Returns ``(seo_text, provenance_tag)`` where provenance_tag is one of
    ``brief_proposed``, ``page_intel_observed``, ``source_intro_fallback``,
    or ``None`` when unresolved.
    """
    provenance: str | None = None
    proposed = brief.get("proposed_meta_description")
    if isinstance(proposed, str) and proposed.strip():
        text = proposed.strip()
        provenance = "brief_proposed"
    else:
        existing = str(pi.get("meta_description") or "").strip()
        if existing:
            text = existing
            provenance = "page_intel_observed"
        else:
            # Last resort: first intro paragraph already in the Markdown body.
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
                return None, None
            provenance = "source_intro_fallback"
    # Strip HTML; keep plain text for Hashnode SEO settings field.
    text = _HTML_TAG_RE.sub("", text).strip()
    text = re.sub(r"\s+", " ", text)
    if len(text) > 160:
        text = text[:157].rstrip() + "…"
    if not text or _INVENTED_FACT_RE.search(text) and text not in body and text not in str(
        pi.get("meta_description") or ""
    ):
        # Allow brief-proposed / observed meta even if pattern-like; block unknowns.
        if text not in str(pi.get("meta_description") or "") and text not in str(
            brief.get("proposed_meta_description") or ""
        ):
            return None, None
    return text, provenance


def _wants_intro_rewrite(
    *,
    ops: list[dict[str, Any]],
    rec_codes: set[str],
    h1: str | None,
    pi: dict[str, Any],
) -> tuple[bool, bool]:
    """Return (should_apply_intro_rewrite, driven_by_meta_only).

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


def _headings_outside_intro(md: str) -> list[str]:
    """Collect ATX heading lines after the first H1 (structure identity)."""
    lines = (md or "").splitlines()
    seen_h1 = False
    out: list[str] = []
    in_fence = False
    for ln in lines:
        if ln.strip().startswith("```"):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        if ln.startswith("# ") and not seen_h1:
            seen_h1 = True
            continue
        if seen_h1 and re.match(r"^#{1,6}\s+", ln):
            out.append(ln.strip())
    return out


def _extract_fences(md: str) -> list[str]:
    return [m.group(1) for m in _CODE_FENCE_RE.finditer(md or "")]


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

    Intro ``rewrite`` ops are applied only when a validated ``proposed``
    replacement is already present on the edit op (content optimization
    layer owns generation). Meta description ops are transported as
    ``seo_description`` metadata only (brief owns proposed-meta provenance;
    never HTML ``<meta>`` in body).
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
    rewrite_provenance: dict[str, Any] | None = None

    ops = _collect_edit_ops(
        brief=brief,
        edit_ops=edit_ops,
        change_plan=change_plan,
        content_drafts=content_drafts,
    )
    # Drop change-plan metadata sentinels (never applied to body).
    ops = [
        op
        for op in ops
        if str(op.get("op_kind") or "") != "_substantive_change_plan"
        and _target_key(op.get("target") or "") != "_substantive_change_plan"
    ]

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

    # Snapshot structure for preservation asserts.
    source_headings = _headings_outside_intro(body)
    source_fences = _extract_fences(body)

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

    # --- meta description → SEO metadata transport (never HTML <meta> in body) ---
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
        seo, seo_prov = _resolve_seo_description(brief=brief, pi=pi, body=body)
        if seo:
            seo_description = seo
            applied_ops.append(meta_ops[0].get("op_id") or "meta_description")
            warnings.append("seo_description_for_hashnode_settings")
            if seo_prov == "brief_proposed":
                warnings.append("seo_description_transported_from_brief")
            elif seo_prov == "page_intel_observed":
                warnings.append("seo_description_transported_from_page_intel")
            elif seo_prov == "source_intro_fallback":
                warnings.append("seo_description_from_source_intro_fallback")
        else:
            warnings.append("insufficient_evidence_meta_description")

    # --- introduction rewrite via validated proposed ---
    wants_intro, meta_only_drive = _wants_intro_rewrite(
        ops=ops, rec_codes=rec_codes, h1=h1, pi=pi
    )
    if meta_only_drive:
        warnings.append("meta_description_does_not_drive_intro_rewrite")

    body_op_applied = False
    if wants_intro:
        intro_op = next(
            (op for op in ops if _is_intro_rewrite_op(op, h1=h1)),
            None,
        )
        proposed_text = ""
        if intro_op and isinstance(intro_op.get("proposed"), str):
            proposed_text = intro_op["proposed"].strip()

        if not proposed_text:
            # No grounded proposal from content opt layer — do NOT invent,
            # reorder, or synthesize. No proposal ⇒ no rewrite.
            warnings.append("intro_rewrite_skipped_no_proposed")
            if intro_op and intro_op.get("target"):
                warnings.append(
                    f"unsupported_edit_op:{intro_op.get('action')}:introduction_without_proposed"
                )
        else:
            original_text = ""
            if intro_op:
                original_text = str(intro_op.get("original") or "").strip()
            evidence = []
            if intro_op:
                evidence = list(intro_op.get("evidence") or [])

            val = validate_proposed_rewrite(
                proposed=proposed_text,
                original=original_text or proposed_text,
                evidence=evidence,
                source_markdown=body,
                h1=h1,
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
                    "proposed_contains_heading",
                    "proposed_invented_url",
                    "proposed_invented_fact",
                    "proposed_is_reorder_only",
                }
                or w.startswith("proposed_ungrounded_tokens:")
            ]
            if hard:
                warnings.extend(hard)
                warnings.append("intro_rewrite_rejected_validation")
            else:
                body, did = _apply_proposed_introduction(body, proposed_text)
                if did:
                    body_op_applied = True
                    if intro_op and intro_op.get("op_id"):
                        applied_ops.append(str(intro_op["op_id"]))
                    applied_ops.append("evidence_grounded_rewrite:introduction")
                    warnings.append("intro_rewrite_applied_from_proposed")
                    rewrite_provenance = {
                        "what_changed": "introduction",
                        "why": (intro_op or {}).get("instruction")
                        or "Answer-first introduction grounded in page evidence.",
                        "related_gap_ids": list(
                            (intro_op or {}).get("related_gap_ids") or []
                        ),
                        "original": original_text,
                        "proposed": proposed_text,
                        "evidence": evidence,
                        "llm_used": False,
                        "paid_retrieval_used": False,
                        "action": "rewrite",
                        "target": "introduction",
                    }
                else:
                    # Already matches proposed (idempotent).
                    warnings.append("intro_rewrite_idempotent_no_change")

    # --- MVP ready FAQ / HowTo promote ops (proposed assembled upstream only) ---
    from aeo_mvp.content.models import FAQ_MIN_EXISTING_QA_PAIRS, HOWTO_MIN_EXISTING_STEPS

    for op in ops:
        if not _is_ready_mvp_body_op(op, h1=h1):
            continue
        op_kind = str(op.get("op_kind") or "")
        proposed_text = str(op.get("proposed") or "").strip()
        if not proposed_text:
            continue
        if op_kind == "add_faq_from_existing_qa":
            # Defensive: never apply below MVP min existing pairs.
            if len(_existing_faq_qa_pairs(body)) < FAQ_MIN_EXISTING_QA_PAIRS:
                warnings.append("faq_op_rejected_insufficient_existing_qa")
                continue
            body, did = _apply_append_block(body, proposed_text)
            if did:
                body_op_applied = True
                if op.get("op_id"):
                    applied_ops.append(str(op["op_id"]))
                applied_ops.append("evidence_grounded_add_faq_from_existing_qa")
                warnings.append("faq_op_applied_from_proposed")
            else:
                warnings.append("faq_op_idempotent_no_change")
        elif op_kind == "add_howto_from_existing_steps":
            steps = _extract_numbered_steps(body)
            if len(steps) < HOWTO_MIN_EXISTING_STEPS:
                for m in re.finditer(
                    r"^Step\s+\d+\s*[:.\-]\s*(.+)$", body or "", re.I | re.M
                ):
                    steps.append(m.group(1).strip())
            if len(steps) < HOWTO_MIN_EXISTING_STEPS:
                warnings.append("howto_op_rejected_insufficient_existing_steps")
                continue
            body, did = _apply_append_block(body, proposed_text)
            if did:
                body_op_applied = True
                if op.get("op_id"):
                    applied_ops.append(str(op["op_id"]))
                applied_ops.append("evidence_grounded_add_howto_from_existing_steps")
                warnings.append("howto_op_applied_from_proposed")
            else:
                warnings.append("howto_op_idempotent_no_change")

    # Author-input-required / deferred ops: never invent; record warning only.
    for op in ops:
        status = str(op.get("status") or "")
        disposition = str(op.get("disposition") or "")
        apply_mode = str(op.get("apply_mode") or "")
        if (
            status == "needs_author_input"
            or disposition == "author_input_required"
            or apply_mode == "author_input_required"
            or str(op.get("op_kind") or "") == "author_input_required"
        ):
            warnings.append(
                "author_input_required:"
                + str(op.get("target") or op.get("op_id") or "unknown")
            )

    # FAQ / HowTo body changes: ready ContentChangeOperation only.
    # Legacy REC_ADD_FAQ_SECTION / REC_ADD_HOWTO_OR_STEPS promote paths are
    # removed (Architect FAIL @ b60f9e7) — they could apply with ≥1 Q&A while
    # MVP lock requires ≥2, and could override needs_author_input ops.
    faq_ready_applied = any(
        "faq" in a.lower() for a in applied_ops
    )
    howto_ready_applied = any(
        "howto" in a.lower() or "steps" in a.lower() for a in applied_ops
    )
    has_faq_op_any_status = any(
        str(op.get("op_kind") or "") == "add_faq_from_existing_qa" for op in ops
    )
    has_howto_op_any_status = any(
        str(op.get("op_kind") or "") == "add_howto_from_existing_steps" for op in ops
    )
    if (
        ("REC_ADD_FAQ_SECTION" in rec_codes or "REC_ADD_QUESTION_HEADINGS" in rec_codes)
        and not faq_ready_applied
    ):
        # Signal: recommendation alone does not promote; need ready op.
        if has_faq_op_any_status:
            warnings.append("legacy_rec_faq_ignored_substantive_op_present")
        warnings.append("insufficient_evidence_faq")
    if "REC_ADD_HOWTO_OR_STEPS" in rec_codes and not howto_ready_applied:
        if has_howto_op_any_status:
            warnings.append("legacy_rec_howto_ignored_substantive_op_present")
        warnings.append("insufficient_evidence_howto")

    # Unsupported actionable ops → warn, leave body alone for those targets.
    for op in ops:
        if _is_retain_h1_op(op) or _is_meta_op(op) or _is_intro_rewrite_op(op, h1=h1):
            continue
        if _is_ready_mvp_body_op(op, h1=h1):
            continue
        if str(op.get("op_kind") or "") in {
            "add_faq_from_existing_qa",
            "add_howto_from_existing_steps",
            "metadata_seo_description",
            "rewrite_introduction",
        }:
            continue
        status = str(op.get("status") or "")
        if status in {"needs_author_input", "unsupported"} or str(
            op.get("disposition") or ""
        ) == "author_input_required":
            continue
        action = op.get("action") or ""
        target = (op.get("target") or "").strip()
        key = _target_key(target)
        t_lower = target.lower()
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

    # Preserve invariants: headings / fences not targeted must survive.
    if source_fences:
        for fence in source_fences:
            if fence not in body:
                warnings.append("invariant_code_fence_corrupted")
                break
    if source_headings:
        after_headings = _headings_outside_intro(body)
        if after_headings != source_headings:
            warnings.append("invariant_headings_altered")

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
        rewrite_provenance=rewrite_provenance,
    )
