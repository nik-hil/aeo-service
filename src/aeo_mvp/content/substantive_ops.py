"""Deterministic substantive change-plan diagnosis (post PR #44).

Maps query → gap → evidence → proposed action/content without inventing facts.
Quality over quantity: never force N edits. Unsupported gaps become
``author_input_required`` (no hallucinated ``proposed``).

Ownership: content optimization layer. Hashnode Markdown generator only
validates + applies already-proposed payloads.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from aeo_mvp.content.models import (
    DEFERRED_OP_KINDS,
    IMPLEMENTED_OP_KINDS,
    GapDisposition,
    OpKind,
)
from aeo_mvp.content.rewrite_proposal import (
    RewriteProposal,
    _clarify_predicate,
    _is_already_answer_first,
    _score_definitional,
    _split_intro_blocks,
    _TEASER_RE,
    propose_introduction_rewrite,
    validate_proposed_rewrite,
)

_HEADING_LINE_RE = re.compile(r"^(#{1,6})\s+(.+)$")
_QUESTION_HEADING_RE = re.compile(
    r"\b(?:what|how|why|when|where|who)\b|\?$",
    re.I,
)
_PROCESS_HEADING_RE = re.compile(
    r"\b(?:loop|flow|steps?|process|running|complete|how)\b",
    re.I,
)
_RELATION_RE = re.compile(
    r"\b(?:decides? what|controls? how|responsible for|combination is|"
    r"not itself|distinction)\b",
    re.I,
)
_VERSION_STEP_RE = re.compile(
    r"^v?\d+\.\d+\s*(?:→|->|—|-)\s*.+$",
    re.I | re.M,
)
_NUMBERED_STEP_RE = re.compile(r"^\d+\.\s+(.+)$", re.M)
_BLOCKQUOTE_RE = re.compile(r"^>\s*(?:\*\*)?(.+?)(?:\*\*)?\s*$", re.M)

# Benefit language must NOT claim ChatGPT/Gemini ranking.
_BENEFIT_BY_KIND: dict[str, str] = {
    "rewrite_introduction": (
        "Improves answer-first extractability of the page lead for probe overlap."
    ),
    "rewrite_section": (
        "Improves section answerability so the heading's core claim is immediately extractable."
    ),
    "add_definition": (
        "Surfaces an on-page definition where a definitional probe expects a concise answer unit."
    ),
    "add_answer_first": (
        "Places a grounded answer immediately under a question-shaped heading."
    ),
    "add_process_summary": (
        "Makes an existing process/sequence scannable as a compact answer unit."
    ),
    "clarify_relationship": (
        "Promotes an on-page relationship statement so model-vs-harness roles are explicit."
    ),
    "author_input_required": (
        "No safe automatic edit; author must supply missing on-page facts before publish."
    ),
}


@dataclass
class SubstantiveChangeItem:
    """One diagnosed change: gap → evidence → action → content → benefit."""

    content_gap: str
    evidence: list[str] = field(default_factory=list)
    proposed_action: str = ""
    proposed_content: str | None = None
    reason: str = ""
    expected_aeo_benefit: str = ""
    op_kind: OpKind | str = "author_input_required"
    disposition: GapDisposition = "author_input_required"
    related_gap_ids: list[str] = field(default_factory=list)
    related_query_ids: list[str] = field(default_factory=list)
    target: str = ""
    action: str = "rewrite"
    original: str | None = None
    query_text: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "content_gap": self.content_gap,
            "evidence": list(self.evidence),
            "proposed_action": self.proposed_action,
            "proposed_content": self.proposed_content,
            "reason": self.reason,
            "expected_aeo_benefit": self.expected_aeo_benefit,
            "op_kind": self.op_kind,
            "disposition": self.disposition,
            "related_gap_ids": list(self.related_gap_ids),
            "related_query_ids": list(self.related_query_ids),
            "target": self.target,
            "action": self.action,
            "original": self.original,
            "query_text": self.query_text,
        }

    def to_edit_op_dict(self) -> dict[str, Any]:
        """Wire shape compatible with EditOp / ContentChange / MD generator."""
        return {
            "action": self.action,
            "target": self.target,
            "target_locator": self.target if self.action != "add" else None,
            "anchor_locator": self.target if self.action == "add" else None,
            "instruction": self.reason,
            "reason": self.reason,
            "related_gap_ids": list(self.related_gap_ids),
            "related_query_ids": list(self.related_query_ids),
            "original": self.original,
            "proposed": self.proposed_content,
            "evidence": list(self.evidence),
            "op_kind": self.op_kind,
            "disposition": self.disposition,
            "expected_aeo_benefit": self.expected_aeo_benefit,
            "op_id": f"sub_{self.op_kind}_{self.target}"[:80],
        }


@dataclass
class SubstantiveChangePlan:
    items: list[SubstantiveChangeItem] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    implemented_op_kinds: list[str] = field(
        default_factory=lambda: sorted(IMPLEMENTED_OP_KINDS)
    )
    deferred_op_kinds: list[str] = field(
        default_factory=lambda: sorted(DEFERRED_OP_KINDS)
    )

    def to_dict(self) -> dict[str, Any]:
        actionable = [i for i in self.items if i.disposition == "actionable"]
        author = [i for i in self.items if i.disposition == "author_input_required"]
        return {
            "items": [i.to_dict() for i in self.items],
            "actionable_count": len(actionable),
            "author_input_required_count": len(author),
            "warnings": list(self.warnings),
            "implemented_op_kinds": list(self.implemented_op_kinds),
            "deferred_op_kinds": list(self.deferred_op_kinds),
        }


def _strip_md_inline(text: str) -> str:
    t = text or ""
    t = re.sub(r"\*\*(.+?)\*\*", r"\1", t)
    t = re.sub(r"\*(.+?)\*", r"\1", t)
    t = re.sub(r"`([^`]+)`", r"\1", t)
    return t.strip()


def split_markdown_sections(md: str) -> list[dict[str, Any]]:
    """Split Markdown into heading-delimited sections (incl. pre-H1 lead)."""
    lines = (md or "").splitlines()
    sections: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    in_fence = False

    def _flush() -> None:
        nonlocal current
        if current is None:
            return
        body = "\n".join(current["body_lines"]).strip("\n")
        current["body"] = body
        current["blocks"] = _paragraph_blocks(body)
        sections.append(current)
        current = None

    for ln in lines:
        if ln.strip().startswith("```"):
            in_fence = not in_fence
            if current is None:
                current = {
                    "level": 0,
                    "heading": "",
                    "heading_line": "",
                    "body_lines": [],
                }
            current["body_lines"].append(ln)
            continue
        if not in_fence:
            m = _HEADING_LINE_RE.match(ln)
            if m:
                _flush()
                current = {
                    "level": len(m.group(1)),
                    "heading": m.group(2).strip(),
                    "heading_line": ln,
                    "body_lines": [],
                }
                continue
        if current is None:
            current = {
                "level": 0,
                "heading": "",
                "heading_line": "",
                "body_lines": [],
            }
        current["body_lines"].append(ln)
    _flush()
    return sections


def _paragraph_blocks(body: str) -> list[str]:
    blocks: list[str] = []
    buf: list[str] = []
    fence_buf: list[str] | None = None
    for ln in (body or "").splitlines():
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
    return [b for b in blocks if b.strip()]


def _section_by_heading(
    sections: list[dict[str, Any]], heading: str
) -> dict[str, Any] | None:
    want = _strip_md_inline(heading).lower()
    for sec in sections:
        if _strip_md_inline(str(sec.get("heading") or "")).lower() == want:
            return sec
    # Fuzzy: heading contained / contains
    for sec in sections:
        h = _strip_md_inline(str(sec.get("heading") or "")).lower()
        if want and (want in h or h in want):
            return sec
    return None


def _definitional_candidates(blocks: list[str]) -> list[tuple[float, str]]:
    out: list[tuple[float, str]] = []
    for block in blocks:
        if block.startswith("```") or block.startswith("|") or block.startswith("!"):
            continue
        plain = _strip_md_inline(block)
        if plain.startswith(">"):
            plain = plain.lstrip("> ").strip()
        score = _score_definitional(plain)
        if score >= 1.0:
            out.append((score, plain))
        for sent in re.split(r"(?<=[.!?])\s+", plain):
            sent = sent.strip()
            if len(sent.split()) < 6:
                continue
            s = _score_definitional(sent)
            if s > 1.0:
                out.append((s, sent))
    out.sort(key=lambda x: (-x[0], len(x[1])))
    return out


def _validate_hard(
    *,
    proposed: str,
    original: str,
    evidence: list[str],
    source_markdown: str,
    h1: str | None = None,
) -> list[str]:
    val = validate_proposed_rewrite(
        proposed=proposed,
        original=original,
        evidence=evidence,
        source_markdown=source_markdown,
        h1=h1,
    )
    return [
        w
        for w in val
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


def _benefit(kind: str) -> str:
    return _BENEFIT_BY_KIND.get(
        kind,
        "Improves grounded answer extractability without inventing claims.",
    )


def _author_input_item(
    *,
    gap: dict[str, Any],
    query_text: str | None,
    reason: str,
    target: str = "",
) -> SubstantiveChangeItem:
    gid = str(gap.get("gap_id") or gap.get("id") or "")
    qids = list(gap.get("query_ids") or [])
    if gap.get("query_id") and str(gap["query_id"]) not in qids:
        qids = [str(gap["query_id"]), *qids]
    return SubstantiveChangeItem(
        content_gap=str(
            gap.get("rationale") or gap.get("explanation") or gap.get("gap_type") or ""
        ),
        evidence=[],
        proposed_action="author_input_required",
        proposed_content=None,
        reason=reason,
        expected_aeo_benefit=_benefit("author_input_required"),
        op_kind="author_input_required",
        disposition="author_input_required",
        related_gap_ids=[gid] if gid else [],
        related_query_ids=qids,
        target=target or "body",
        action="rewrite",
        original=None,
        query_text=query_text,
    )


def propose_section_lead_rewrite(
    *,
    source_markdown: str,
    heading: str,
    reason: str = "Answer-first section lead grounded in section evidence.",
    related_gap_ids: list[str] | None = None,
    related_query_ids: list[str] | None = None,
    op_kind: OpKind | str = "rewrite_section",
) -> SubstantiveChangeItem | None:
    """Rewrite a non-intro section lead from section-local definitional evidence."""
    sections = split_markdown_sections(source_markdown)
    sec = _section_by_heading(sections, heading)
    if not sec or not sec.get("heading"):
        return None
    # Intro / H1 body is owned by rewrite_introduction.
    if sec.get("level") == 1 and sections and sections[0] is sec:
        h1_line, _, _ = _split_intro_blocks(source_markdown)
        if h1_line and sec.get("heading_line") == h1_line:
            return None

    blocks = list(sec.get("blocks") or [])
    if not blocks:
        return None
    if _is_already_answer_first(blocks[:1]):
        return None

    candidates = _definitional_candidates(blocks)
    if not candidates:
        return None
    best_score, lead_source = candidates[0]
    if best_score < 2.0:
        return None

    # Prefer clarify-in-place over invented structure when not becomes-when form.
    lead_proposed = _clarify_predicate(lead_source)
    if not lead_proposed.endswith((".", "!", "?")):
        lead_proposed = lead_proposed + "."
    if lead_proposed.strip() == lead_source.strip() and not _TEASER_RE.search(
        blocks[0]
    ):
        # Still allow promotion: move definitional sentence to lead when buried.
        if blocks[0].strip() == lead_source.strip() or lead_source in blocks[0]:
            return None

    remaining: list[str] = []
    for block in blocks:
        plain = _strip_md_inline(block)
        if plain.startswith(">"):
            plain = plain.lstrip("> ").strip()
        if plain.strip() == lead_source.strip():
            continue
        if lead_source.strip() in plain and not block.startswith("```"):
            trimmed = plain.replace(lead_source.strip(), "", 1).strip()
            if trimmed:
                remaining.append(trimmed)
            continue
        if _TEASER_RE.search(plain) and len(plain.split()) < 20:
            continue
        remaining.append(block if block.startswith("```") else plain)

    proposed = "\n\n".join([lead_proposed, *remaining]).strip()
    original = "\n\n".join(blocks).strip()
    if not proposed or proposed == original:
        return None

    evidence = [lead_source]
    for _score, cand in candidates[1:4]:
        if cand not in evidence:
            evidence.append(cand)

    hard = _validate_hard(
        proposed=proposed,
        original=original,
        evidence=evidence,
        source_markdown=source_markdown,
    )
    if hard:
        return None

    return SubstantiveChangeItem(
        content_gap=f"Section '{heading}' lacks an answer-first lead",
        evidence=evidence,
        proposed_action=f"rewrite_section:{heading}",
        proposed_content=proposed,
        reason=reason,
        expected_aeo_benefit=_benefit(str(op_kind)),
        op_kind=op_kind,
        disposition="actionable",
        related_gap_ids=list(related_gap_ids or []),
        related_query_ids=list(related_query_ids or []),
        target=f"section:{heading}",
        action="rewrite",
        original=original,
    )


def propose_add_definition(
    *,
    source_markdown: str,
    heading: str,
    reason: str = "Add concise on-page definition under the heading.",
    related_gap_ids: list[str] | None = None,
    related_query_ids: list[str] | None = None,
) -> SubstantiveChangeItem | None:
    """Insert a grounded definitional sentence after a heading when lead is weak."""
    sections = split_markdown_sections(source_markdown)
    sec = _section_by_heading(sections, heading)
    if not sec:
        return None
    blocks = list(sec.get("blocks") or [])
    candidates = _definitional_candidates(blocks)
    # Also allow article-wide definitions when section is question-shaped but thin.
    if not candidates:
        all_blocks: list[str] = []
        for s in sections:
            all_blocks.extend(s.get("blocks") or [])
        candidates = _definitional_candidates(all_blocks)
    if not candidates:
        return None
    _score, definition = candidates[0]
    if _score < 2.0:
        return None

    first = _strip_md_inline(blocks[0]) if blocks else ""
    if first and (
        definition.strip() in first
        or _score_definitional(first) >= 4.0
    ):
        return None

    proposed = definition.strip()
    if not proposed.endswith((".", "!", "?")):
        proposed += "."
    hard = _validate_hard(
        proposed=proposed,
        original=first or "",
        evidence=[definition],
        source_markdown=source_markdown,
    )
    # insert may equal a buried sentence — allow when not already lead.
    hard = [w for w in hard if w != "proposed_is_reorder_only"]
    if hard:
        return None

    return SubstantiveChangeItem(
        content_gap=f"Heading '{heading}' needs a concise definitional answer unit",
        evidence=[definition],
        proposed_action=f"add_definition:{heading}",
        proposed_content=proposed,
        reason=reason,
        expected_aeo_benefit=_benefit("add_definition"),
        op_kind="add_definition",
        disposition="actionable",
        related_gap_ids=list(related_gap_ids or []),
        related_query_ids=list(related_query_ids or []),
        target=f"section:{heading}",
        action="add",
        original=first or None,
    )


def propose_clarify_relationship(
    *,
    source_markdown: str,
    heading: str,
    reason: str = "Promote on-page relationship statement to section lead.",
    related_gap_ids: list[str] | None = None,
    related_query_ids: list[str] | None = None,
) -> SubstantiveChangeItem | None:
    sections = split_markdown_sections(source_markdown)
    sec = _section_by_heading(sections, heading)
    if not sec:
        return None
    blocks = list(sec.get("blocks") or [])
    body = "\n".join(blocks)
    relation: str | None = None
    for m in _BLOCKQUOTE_RE.finditer(body):
        cand = _strip_md_inline(m.group(1))
        if _RELATION_RE.search(cand) and len(cand.split()) >= 6:
            relation = cand.strip()
            break
    if not relation:
        for block in blocks:
            plain = _strip_md_inline(block)
            if plain.startswith("```"):
                continue
            if _RELATION_RE.search(plain) and 6 <= len(plain.split()) <= 40:
                relation = plain.strip()
                break
    if not relation:
        return None
    first = _strip_md_inline(blocks[0]) if blocks else ""
    if first and relation in first:
        return None

    proposed = relation if relation.endswith((".", "!", "?")) else relation + "."
    hard = _validate_hard(
        proposed=proposed,
        original=first or "",
        evidence=[relation],
        source_markdown=source_markdown,
    )
    hard = [w for w in hard if w != "proposed_is_reorder_only"]
    if hard:
        return None

    return SubstantiveChangeItem(
        content_gap=f"Section '{heading}' buries a key relationship statement",
        evidence=[relation],
        proposed_action=f"clarify_relationship:{heading}",
        proposed_content=proposed,
        reason=reason,
        expected_aeo_benefit=_benefit("clarify_relationship"),
        op_kind="clarify_relationship",
        disposition="actionable",
        related_gap_ids=list(related_gap_ids or []),
        related_query_ids=list(related_query_ids or []),
        target=f"section:{heading}",
        action="add",
        original=first or None,
    )


def extract_process_steps(source_markdown: str) -> list[str]:
    """Extract grounded process/sequence fragments already present on-page."""
    steps: list[str] = []
    for m in _NUMBERED_STEP_RE.finditer(source_markdown or ""):
        text = _strip_md_inline(m.group(1))
        if text.startswith("_") and text.endswith("_"):
            continue
        if text and text not in steps:
            steps.append(text)
    for m in _VERSION_STEP_RE.finditer(source_markdown or ""):
        text = _strip_md_inline(m.group(0))
        if text and text not in steps:
            steps.append(text)
    # Fence lines like "v0.1 → basic tool calling"
    for m in re.finditer(
        r"^(v\d+\.\d+\s*→\s*.+)$", source_markdown or "", re.M | re.I
    ):
        text = m.group(1).strip()
        if text and text not in steps:
            steps.append(text)
    return steps


def propose_process_summary(
    *,
    source_markdown: str,
    heading: str | None = None,
    reason: str = "Add concise process/sequence summary from on-page steps.",
    related_gap_ids: list[str] | None = None,
    related_query_ids: list[str] | None = None,
) -> SubstantiveChangeItem | None:
    steps = extract_process_steps(source_markdown)
    if len(steps) < 2:
        return None

    target_heading = heading
    if not target_heading:
        sections = split_markdown_sections(source_markdown)
        for sec in sections:
            h = str(sec.get("heading") or "")
            if h and _PROCESS_HEADING_RE.search(h):
                target_heading = h
                break
    if not target_heading:
        return None

    sec = _section_by_heading(split_markdown_sections(source_markdown), target_heading)
    if not sec:
        return None
    body_l = (sec.get("body") or "").lower()
    # Idempotent: section already opens with a compact multi-step summary.
    if " → " in (sec.get("blocks") or [""])[0] and len(steps) <= 3:
        lead0 = (sec.get("blocks") or [""])[0]
        if all(any(tok.lower() in lead0.lower() for tok in s.split()[:2]) for s in steps[:2]):
            return None
    if re.search(r"^1\.\s+", sec.get("body") or "", re.M) and len(
        extract_process_steps(sec.get("body") or "")
    ) >= 3:
        return None

    # Compose ONLY from extracted step texts — no invented verbs/facts.
    use = steps[:6]
    if all("→" in s or "->" in s for s in use):
        proposed = "Sequence: " + "; ".join(use) + "."
    else:
        proposed = "Process overview:\n\n" + "\n".join(
            f"{i}. {s}" for i, s in enumerate(use, start=1)
        )

    evidence = list(use)
    hard = _validate_hard(
        proposed=proposed,
        original="",
        evidence=evidence,
        source_markdown=source_markdown,
    )
    hard = [
        w
        for w in hard
        if w
        not in {
            "proposed_is_reorder_only",
            "proposed_identical_to_original",
        }
    ]
    # "Sequence" / "Process overview" glue tokens — allow explicitly.
    hard = [
        w
        for w in hard
        if not (
            w.startswith("proposed_ungrounded_tokens:")
            and set(w.split(":", 1)[1].split(",")).issubset(
                {"sequence", "process", "overview"}
            )
        )
    ]
    if hard:
        # Fall back to a pure join without glue nouns when validation is strict.
        proposed_alt = " → ".join(use)
        hard2 = _validate_hard(
            proposed=proposed_alt,
            original="",
            evidence=evidence,
            source_markdown=source_markdown,
        )
        hard2 = [
            w
            for w in hard2
            if w
            not in {
                "proposed_is_reorder_only",
                "proposed_identical_to_original",
            }
        ]
        if hard2:
            return None
        proposed = proposed_alt

    # Skip if the exact summary text already appears.
    if proposed.strip() in (source_markdown or ""):
        return None
    if proposed.strip().lower() in body_l:
        return None

    return SubstantiveChangeItem(
        content_gap=f"Process/sequence under '{target_heading}' is not scannable as an answer unit",
        evidence=evidence,
        proposed_action=f"add_process_summary:{target_heading}",
        proposed_content=proposed,
        reason=reason,
        expected_aeo_benefit=_benefit("add_process_summary"),
        op_kind="add_process_summary",
        disposition="actionable",
        related_gap_ids=list(related_gap_ids or []),
        related_query_ids=list(related_query_ids or []),
        target=f"section:{target_heading}",
        action="add",
        original=None,
    )


def _gap_dicts(gaps: list[Any] | None) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for g in gaps or []:
        if isinstance(g, dict):
            out.append(g)
        elif hasattr(g, "to_dict"):
            out.append(g.to_dict())
    return out


def _query_text_for_gap(
    gap: dict[str, Any], coverage_by_query: list[dict[str, Any]]
) -> str | None:
    qid = str(gap.get("query_id") or "")
    for row in coverage_by_query:
        if str(row.get("query_id") or "") == qid and row.get("query_text"):
            return str(row["query_text"])
    for qid2 in gap.get("query_ids") or []:
        for row in coverage_by_query:
            if str(row.get("query_id") or "") == str(qid2) and row.get("query_text"):
                return str(row["query_text"])
    return None


def build_substantive_change_plan(
    *,
    source_markdown: str,
    gaps: list[Any] | None = None,
    coverage_by_query: list[dict[str, Any]] | None = None,
    page_intelligence: dict[str, Any] | None = None,
    existing_ops: list[dict[str, Any]] | None = None,
    h1: str | None = None,
) -> SubstantiveChangePlan:
    """Diagnose substantive changes from gaps + source evidence.

    Does not force a fixed number of edits. Emits actionable items only when
    proposed content validates against on-page evidence; otherwise
    ``author_input_required``.
    """
    warnings: list[str] = []
    items: list[SubstantiveChangeItem] = []
    pi = page_intelligence or {}
    gap_rows = _gap_dicts(gaps)
    coverage = list(coverage_by_query or [])
    sections = split_markdown_sections(source_markdown)
    resolved_h1 = h1 or str(pi.get("h1") or pi.get("title") or "").strip() or None
    if not resolved_h1:
        m = re.search(r"^#\s+(.+)$", source_markdown or "", re.M)
        if m:
            resolved_h1 = m.group(1).strip()

    seen_targets: set[str] = set()
    # Track op kinds already requested by existing brief ops.
    for op in existing_ops or []:
        if not isinstance(op, dict):
            continue
        t = str(
            op.get("target") or op.get("target_locator") or op.get("anchor_locator") or ""
        )
        if t:
            seen_targets.add(t.lower())

    # --- 1) Introduction rewrite when answer-first gap / weak intro ---
    ans = pi.get("answerability_signals") or pi.get("answerability") or {}
    needs_intro = False
    intro_gap_ids: list[str] = []
    intro_query_ids: list[str] = []
    for g in gap_rows:
        gt = str(g.get("gap_type") or "").lower()
        kind = str(g.get("kind") or "").lower()
        if (
            "answer" in gt
            or kind in {"missing_faq", "missing_answer", "no_answer_first"}
            or "answer_first" in str(g.get("gap_id") or "")
            or g.get("page_coverage") in {"thin", "absent", "mismatched"}
        ):
            # Prefer explicit answer-first gaps; thin coverage alone is weaker.
            if "answer" in gt or "answer_first" in str(g.get("gap_id") or "") or kind in {
                "missing_faq",
                "missing_answer",
            }:
                needs_intro = True
                gid = str(g.get("gap_id") or g.get("id") or "")
                if gid:
                    intro_gap_ids.append(gid)
                if g.get("query_id"):
                    intro_query_ids.append(str(g["query_id"]))
    if isinstance(ans, dict) and ans.get("answer_first_heuristic") is False:
        needs_intro = True
    limits = pi.get("limits") or []
    if "no_answer_first" in limits:
        needs_intro = True
    # Also when an existing intro rewrite op is present.
    for op in existing_ops or []:
        if not isinstance(op, dict):
            continue
        action = str(op.get("action") or "").lower()
        target = str(
            op.get("target") or op.get("target_locator") or op.get("anchor_locator") or ""
        )
        instr = str(op.get("instruction") or op.get("reason") or "").lower()
        if action in {"rewrite", "expand"} and (
            "intro" in target.lower()
            or target.lower() in {"introduction", "opening"}
            or "answer-first" in instr
            or (resolved_h1 and target.lower() == f"section:{resolved_h1}".lower())
        ):
            needs_intro = True
            intro_gap_ids.extend(str(x) for x in (op.get("related_gap_ids") or []))
            intro_query_ids.extend(str(x) for x in (op.get("related_query_ids") or []))

    if needs_intro and source_markdown.strip():
        proposal = propose_introduction_rewrite(
            source_markdown=source_markdown,
            page_intelligence=pi,
            related_gap_ids=list(dict.fromkeys(intro_gap_ids)),
        )
        if proposal is not None:
            items.append(
                SubstantiveChangeItem(
                    content_gap="Introduction is not answer-first / weakly extractable",
                    evidence=list(proposal.evidence),
                    proposed_action="rewrite_introduction",
                    proposed_content=proposal.proposed,
                    reason=proposal.reason
                    or "Answer-first introduction grounded in page evidence.",
                    expected_aeo_benefit=_benefit("rewrite_introduction"),
                    op_kind="rewrite_introduction",
                    disposition="actionable",
                    related_gap_ids=list(proposal.related_gap_ids or intro_gap_ids),
                    related_query_ids=list(dict.fromkeys(intro_query_ids)),
                    target="introduction",
                    action="rewrite",
                    original=proposal.original,
                )
            )
            seen_targets.add("introduction")
            if resolved_h1:
                seen_targets.add(f"section:{resolved_h1}".lower())
        else:
            warnings.append("intro_rewrite_no_grounded_proposal")

    # --- 2) Per-gap diagnosis for query coverage / structure gaps ---
    for g in gap_rows:
        gid = str(g.get("gap_id") or g.get("id") or "")
        gt = str(g.get("gap_type") or "").lower()
        kind = str(g.get("kind") or "").lower()
        qtext = _query_text_for_gap(g, coverage)
        qids = list(g.get("query_ids") or [])
        if g.get("query_id") and str(g["query_id"]) not in qids:
            qids = [str(g["query_id"]), *qids]

        # Annotate gap disposition later via returned plan items.
        if gt in {"schema_gap", "metadata", "technical_extractability_gap"}:
            # Not MD-body substantive content — skip (meta handled elsewhere).
            continue
        if gt in {"false_coverage_nav", "genre_mismatch"}:
            items.append(
                _author_input_item(
                    gap=g,
                    query_text=qtext,
                    reason=(
                        "Gap type requires editorial judgment / site structure change; "
                        "no automatic body invent."
                    ),
                )
            )
            continue

        # Choose a heading target from query keywords / question headings.
        target_heading: str | None = None
        q_l = (qtext or "").lower()
        for sec in sections:
            h = str(sec.get("heading") or "")
            if not h or (resolved_h1 and h.lower() == resolved_h1.lower()):
                continue
            h_l = h.lower()
            if q_l and any(
                tok and tok in h_l
                for tok in re.findall(r"[a-z0-9]{4,}", q_l)[:6]
            ):
                target_heading = h
                break
            if _QUESTION_HEADING_RE.search(h) and (
                "definition" in gt
                or "question" in gt
                or "thin" in gt
                or "missing" in gt
                or kind in {"missing_answer", "thin_passage"}
            ):
                target_heading = h
                break

        if not target_heading:
            # Process-shaped gaps → process heading
            if (
                "howto" in gt
                or "step" in kind
                or "missing_steps" in kind
                or (q_l and any(w in q_l for w in ("how", "loop", "flow", "steps")))
            ):
                for sec in sections:
                    h = str(sec.get("heading") or "")
                    if h and _PROCESS_HEADING_RE.search(h):
                        target_heading = h
                        break

        # Attempt grounded proposals for this gap (at most one actionable).
        proposed_item: SubstantiveChangeItem | None = None
        if target_heading:
            tkey = f"section:{target_heading}".lower()
            if tkey not in seen_targets:
                if _QUESTION_HEADING_RE.search(target_heading) or (
                    q_l and any(w in q_l for w in ("what is", "what are", "define"))
                ):
                    proposed_item = propose_add_definition(
                        source_markdown=source_markdown,
                        heading=target_heading,
                        related_gap_ids=[gid] if gid else [],
                        related_query_ids=qids,
                    )
                    if proposed_item is None:
                        proposed_item = propose_section_lead_rewrite(
                            source_markdown=source_markdown,
                            heading=target_heading,
                            related_gap_ids=[gid] if gid else [],
                            related_query_ids=qids,
                            op_kind="add_answer_first",
                        )
                        if proposed_item is not None:
                            proposed_item.op_kind = "add_answer_first"
                            proposed_item.action = "add"
                            # For add_answer_first, proposed is the lead sentence only.
                            if proposed_item.evidence:
                                proposed_item.proposed_content = (
                                    proposed_item.evidence[0]
                                    if proposed_item.evidence[0].endswith((".", "!", "?"))
                                    else proposed_item.evidence[0] + "."
                                )
                                proposed_item.proposed_action = (
                                    f"add_answer_first:{target_heading}"
                                )
                elif _PROCESS_HEADING_RE.search(target_heading) or (
                    q_l and any(w in q_l for w in ("how", "loop", "flow", "process"))
                ):
                    proposed_item = propose_clarify_relationship(
                        source_markdown=source_markdown,
                        heading=target_heading,
                        related_gap_ids=[gid] if gid else [],
                        related_query_ids=qids,
                    )
                    if proposed_item is None:
                        proposed_item = propose_process_summary(
                            source_markdown=source_markdown,
                            heading=target_heading,
                            related_gap_ids=[gid] if gid else [],
                            related_query_ids=qids,
                        )
                    if proposed_item is None:
                        proposed_item = propose_section_lead_rewrite(
                            source_markdown=source_markdown,
                            heading=target_heading,
                            related_gap_ids=[gid] if gid else [],
                            related_query_ids=qids,
                        )
                else:
                    proposed_item = propose_section_lead_rewrite(
                        source_markdown=source_markdown,
                        heading=target_heading,
                        related_gap_ids=[gid] if gid else [],
                        related_query_ids=qids,
                    )

        if proposed_item is not None:
            if qtext:
                proposed_item.query_text = qtext
                proposed_item.content_gap = (
                    f"Query '{qtext}' under-covered — {proposed_item.content_gap}"
                )
            items.append(proposed_item)
            seen_targets.add(proposed_item.target.lower())
            continue

        # Query coverage gaps without groundable body evidence → author input.
        if g.get("page_coverage") in {"absent", "thin", "mismatched"} or gt in {
            "thin_coverage",
            "missing_page",
            "question_coverage_gap",
            "evidence_gap",
        }:
            # Avoid flooding: only when we have a query_id and no intro already covering it.
            if not qids and not qtext:
                continue
            # Skip if intro rewrite already cites this gap.
            if any(
                gid and gid in (it.related_gap_ids or [])
                for it in items
                if it.disposition == "actionable"
            ):
                continue
            items.append(
                _author_input_item(
                    gap=g,
                    query_text=qtext,
                    reason=(
                        "No on-page evidence strong enough to ground an automatic edit "
                        f"for query {qtext!r}; author input required."
                    ),
                    target=f"section:{target_heading}" if target_heading else "body",
                )
            )

    # --- 3) Opportunistic process summary when howto gap exists and steps present ---
    has_howto_gap = any(
        "howto" in str(g.get("gap_type") or "").lower()
        or str(g.get("kind") or "") in {"missing_steps", "missing_faq"}
        or "step" in str(g.get("kind") or "").lower()
        for g in gap_rows
    )
    if has_howto_gap:
        howto_gaps = [
            g
            for g in gap_rows
            if "howto" in str(g.get("gap_type") or "").lower()
            or str(g.get("kind") or "") in {"missing_steps", "missing_faq"}
        ]
        g0 = howto_gaps[0] if howto_gaps else {}
        gid = str(g0.get("gap_id") or g0.get("id") or "")
        proc = propose_process_summary(
            source_markdown=source_markdown,
            related_gap_ids=[gid] if gid else [],
            related_query_ids=list(g0.get("query_ids") or []),
        )
        if proc is not None and proc.target.lower() not in seen_targets:
            items.append(proc)
            seen_targets.add(proc.target.lower())

    # --- 4) Existing section rewrite ops without proposals — try fill or author_input ---
    for op in existing_ops or []:
        if not isinstance(op, dict):
            continue
        action = str(op.get("action") or "").lower()
        target = str(
            op.get("target") or op.get("target_locator") or op.get("anchor_locator") or ""
        )
        if action not in {"rewrite", "expand", "add"}:
            continue
        if not target.lower().startswith("section:"):
            continue
        heading = target.split(":", 1)[1].strip()
        if resolved_h1 and heading.lower() == resolved_h1.lower():
            continue  # intro path
        if target.lower() in seen_targets:
            continue
        if isinstance(op.get("proposed"), str) and op["proposed"].strip():
            continue
        related = [str(x) for x in (op.get("related_gap_ids") or [])]
        rq = [str(x) for x in (op.get("related_query_ids") or [])]
        filled = propose_section_lead_rewrite(
            source_markdown=source_markdown,
            heading=heading,
            reason=str(op.get("instruction") or op.get("reason") or ""),
            related_gap_ids=related,
            related_query_ids=rq,
        )
        if filled is None and action == "add":
            filled = propose_add_definition(
                source_markdown=source_markdown,
                heading=heading,
                related_gap_ids=related,
                related_query_ids=rq,
            )
        if filled is not None:
            items.append(filled)
            seen_targets.add(filled.target.lower())
        else:
            items.append(
                SubstantiveChangeItem(
                    content_gap=str(op.get("instruction") or op.get("reason") or target),
                    evidence=[],
                    proposed_action="author_input_required",
                    proposed_content=None,
                    reason=(
                        "Existing edit op could not be grounded from on-page evidence; "
                        "author input required (no invented content)."
                    ),
                    expected_aeo_benefit=_benefit("author_input_required"),
                    op_kind="author_input_required",
                    disposition="author_input_required",
                    related_gap_ids=related,
                    related_query_ids=rq,
                    target=target,
                    action=action,
                )
            )

    # Deduplicate actionable by target+op_kind; prefer actionable over author_input.
    deduped: list[SubstantiveChangeItem] = []
    seen_keys: set[str] = set()
    # Actionable first
    for it in items:
        if it.disposition != "actionable":
            continue
        key = f"{it.op_kind}|{it.target.lower()}"
        if key in seen_keys:
            continue
        seen_keys.add(key)
        deduped.append(it)
    for it in items:
        if it.disposition == "actionable":
            continue
        key = f"air|{it.target.lower()}|{it.content_gap[:40]}"
        if key in seen_keys:
            continue
        # Skip author_input when we already have actionable for same gap id.
        if it.related_gap_ids and any(
            gid in (a.related_gap_ids or []) for a in deduped for gid in it.related_gap_ids
        ):
            continue
        seen_keys.add(key)
        deduped.append(it)

    return SubstantiveChangePlan(items=deduped, warnings=warnings)


def annotate_gaps_with_disposition(
    gaps: list[dict[str, Any]],
    plan: SubstantiveChangePlan,
) -> list[dict[str, Any]]:
    """Return gap dicts annotated with disposition / recommended_op_kind."""
    by_gap: dict[str, SubstantiveChangeItem] = {}
    for it in plan.items:
        for gid in it.related_gap_ids:
            # Prefer actionable annotation.
            prev = by_gap.get(gid)
            if prev is None or (
                prev.disposition != "actionable" and it.disposition == "actionable"
            ):
                by_gap[gid] = it
    out: list[dict[str, Any]] = []
    for g in gaps:
        row = dict(g)
        gid = str(row.get("gap_id") or row.get("id") or "")
        it = by_gap.get(gid)
        if it is not None:
            row["disposition"] = it.disposition
            row["recommended_op_kind"] = it.op_kind
        elif not row.get("disposition"):
            # Readiness / meta gaps without plan entries stay unmarked.
            pass
        out.append(row)
    return out


def merge_plan_into_ops(
    ops: list[dict[str, Any]],
    plan: SubstantiveChangePlan,
) -> list[dict[str, Any]]:
    """Merge substantive plan items onto edit ops; append new actionable ops."""
    enriched: list[dict[str, Any]] = [dict(op) for op in ops if isinstance(op, dict)]

    def _target_key(op: dict[str, Any]) -> str:
        return str(
            op.get("target") or op.get("target_locator") or op.get("anchor_locator") or ""
        ).strip().lower()

    by_target: dict[str, dict[str, Any]] = {}
    for op in enriched:
        k = _target_key(op)
        if k:
            by_target[k] = op

    for it in plan.items:
        if it.disposition != "actionable" or not it.proposed_content:
            # Mark matching ops as author_input_required when applicable.
            if it.disposition == "author_input_required":
                k = it.target.lower()
                if k in by_target:
                    by_target[k]["disposition"] = "author_input_required"
                    by_target[k]["op_kind"] = "author_input_required"
                    by_target[k]["proposed"] = None
                    by_target[k]["reason"] = it.reason
                    by_target[k]["expected_aeo_benefit"] = it.expected_aeo_benefit
            continue

        payload = it.to_edit_op_dict()
        keys_to_try = [it.target.lower()]
        if it.op_kind == "rewrite_introduction":
            keys_to_try.extend(
                ["introduction", "intro", "opening", payload["target"].lower()]
            )

        matched = None
        for k in keys_to_try:
            if k in by_target:
                matched = by_target[k]
                break
        # Match intro ops targeting section:H1
        if matched is None and it.op_kind == "rewrite_introduction":
            for op in enriched:
                action = str(op.get("action") or "").lower()
                instr = str(op.get("instruction") or op.get("reason") or "").lower()
                t = _target_key(op)
                if action in {"rewrite", "expand"} and (
                    t in {"introduction", "intro", "opening"}
                    or "answer-first" in instr
                    or t.startswith("section:")
                ):
                    matched = op
                    break

        if matched is not None:
            matched["original"] = it.original
            matched["proposed"] = it.proposed_content
            matched["evidence"] = list(it.evidence)
            matched["op_kind"] = it.op_kind
            matched["disposition"] = "actionable"
            matched["expected_aeo_benefit"] = it.expected_aeo_benefit
            if it.reason and not matched.get("reason"):
                matched["reason"] = it.reason
            if it.related_gap_ids and not matched.get("related_gap_ids"):
                matched["related_gap_ids"] = list(it.related_gap_ids)
            if it.related_query_ids and not matched.get("related_query_ids"):
                matched["related_query_ids"] = list(it.related_query_ids)
        else:
            enriched.append(payload)
            by_target[it.target.lower()] = payload

    # Append author_input_required sentinel ops not already represented.
    for it in plan.items:
        if it.disposition != "author_input_required":
            continue
        if it.target.lower() in by_target and by_target[it.target.lower()].get(
            "disposition"
        ) == "author_input_required":
            continue
        if any(
            str(op.get("op_kind") or "") == "author_input_required"
            and set(op.get("related_gap_ids") or []) & set(it.related_gap_ids or [])
            for op in enriched
        ):
            continue
        enriched.append(it.to_edit_op_dict())

    return enriched
