"""MVP change-plan diagnosis (Architect + Content Optimizer design lock).

Locked ready apply kinds:
- rewrite_introduction (PR #44 path)
- metadata_seo_description (metadata_only; not a body edit)
- add_faq_from_existing_qa (≥N existing on-page Q&A pairs)
- add_howto_from_existing_steps (≥3 existing numbered / Step N lines)
- rewrite_section (primary grounded LLM; draft_paid + key)
- add_explanation (secondary grounded LLM; draft_paid + key)

clarify_relationship remains deferred. Never invent facts, Q/A, steps, URLs,
schema, or ranking claims. Prefer 1–2 strong grounded section ops.

Ownership: content optimization layer. Hashnode MD generator consumes
``status=ready`` ops only (apply/validate); it must not invent ``proposed``
and must never call the LLM.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from aeo_mvp.content.grounded_synth import (
    MAX_GROUNDED_BODY_OPS,
    OpenAICompatibleChat,
    select_section_for_query,
    synthesize_add_explanation,
    synthesize_rewrite_section,
)
from aeo_mvp.content.models import (
    DEFERRED_OP_KINDS,
    FAQ_MIN_EXISTING_QA_PAIRS,
    HOWTO_MIN_EXISTING_STEPS,
    IMPLEMENTED_OP_KINDS,
    ApplyMode,
    ContentChangeOperation,
    GapDisposition,
    OpKind,
    OpStatus,
)
from aeo_mvp.content.rewrite_proposal import propose_introduction_rewrite

_STEP_N_RE = re.compile(r"^Step\s+(\d+)\s*[:.\-]\s*(.+)$", re.I | re.M)
_NUMBERED_STEP_RE = re.compile(r"^\d+\.\s+(.+)$", re.M)

_BENEFIT: dict[str, str] = {
    "rewrite_introduction": (
        "Improves answer-first extractability of the page lead for probe overlap."
    ),
    "metadata_seo_description": (
        "Transports an SEO description for Hashnode settings without changing body Markdown."
    ),
    "add_faq_from_existing_qa": (
        "Surfaces already-present question/answer units as a scannable FAQ block."
    ),
    "add_howto_from_existing_steps": (
        "Surfaces already-present numbered steps as a scannable Steps section."
    ),
    "rewrite_section": (
        "Rewrites a bounded section using only in-section evidence for probe overlap."
    ),
    "add_explanation": (
        "Inserts a short clarifying explanation grounded in on-page evidence."
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
    target_kind: str = ""
    action: str = "rewrite"
    original: str | None = None
    query_text: str | None = None
    apply_mode: ApplyMode = "author_input_required"
    status: OpStatus = "needs_author_input"
    claims: list[dict[str, str]] = field(default_factory=list)
    llm_used: bool = False

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
            "target_kind": self.target_kind,
            "action": self.action,
            "original": self.original,
            "query_text": self.query_text,
            "apply_mode": self.apply_mode,
            "status": self.status,
            "claims": list(self.claims),
            "llm_used": self.llm_used,
        }

    def to_operation(self) -> ContentChangeOperation:
        return ContentChangeOperation(
            action=self.action,  # type: ignore[arg-type]
            target_kind=self.target_kind or str(self.op_kind),
            target_locator=self.target or None,
            original=self.original,
            proposed=self.proposed_content,
            evidence=list(self.evidence),
            claims=list(self.claims),
            related_gap_ids=list(self.related_gap_ids),
            related_query_ids=list(self.related_query_ids),
            reason=self.reason,
            apply_mode=self.apply_mode,
            status=self.status,
            op_kind=self.op_kind,
            expected_aeo_benefit=self.expected_aeo_benefit,
            disposition=self.disposition,
            op_id=f"mvp_{self.op_kind}_{self.target or self.target_kind}"[:80],
        )

    def to_edit_op_dict(self) -> dict[str, Any]:
        return self.to_operation().to_edit_op_dict()


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
        ready = [i for i in self.items if i.status == "ready"]
        author = [i for i in self.items if i.status == "needs_author_input"]
        return {
            "items": [i.to_dict() for i in self.items],
            "actionable_count": len(ready),
            "author_input_required_count": len(author),
            "ready_count": len(ready),
            "needs_author_input_count": len(author),
            "warnings": list(self.warnings),
            "implemented_op_kinds": list(self.implemented_op_kinds),
            "deferred_op_kinds": list(self.deferred_op_kinds),
        }


def _benefit(kind: str) -> str:
    return _BENEFIT.get(
        kind,
        "Improves grounded answer extractability without inventing claims.",
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


def extract_existing_qa_pairs(source_markdown: str) -> list[tuple[str, str]]:
    """Collect existing question headings + following answer paragraphs.

    Never invents Q or A. Skips fenced code.
    """
    lines = (source_markdown or "").splitlines()
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


def assemble_faq_block(qa_pairs: list[tuple[str, str]], *, limit: int = 5) -> str:
    """Assemble FAQ Markdown solely from existing Q&A pairs."""
    parts = ["## FAQ", ""]
    for q, a in qa_pairs[:limit]:
        parts.append(f"### {q}")
        parts.append("")
        parts.append(a)
        parts.append("")
    return "\n".join(parts).rstrip() + "\n"


def extract_existing_steps(source_markdown: str) -> list[str]:
    """Extract existing numbered steps or ``Step N:`` lines. Never invents."""
    steps: list[str] = []
    for m in _NUMBERED_STEP_RE.finditer(source_markdown or ""):
        text = m.group(1).strip()
        if text.startswith("_") and text.endswith("_"):
            continue
        if text and text not in steps:
            steps.append(text)
    for m in _STEP_N_RE.finditer(source_markdown or ""):
        text = m.group(2).strip()
        if text and text not in steps:
            steps.append(text)
    return steps


def assemble_howto_block(steps: list[str], *, limit: int = 8) -> str:
    """Assemble Steps section solely from existing step lines."""
    parts = ["## Steps", ""]
    for i, step in enumerate(steps[:limit], start=1):
        parts.append(f"{i}. {step}")
    parts.append("")
    return "\n".join(parts)


def propose_faq_from_existing_qa(
    *,
    source_markdown: str,
    related_gap_ids: list[str] | None = None,
    related_query_ids: list[str] | None = None,
    min_pairs: int = FAQ_MIN_EXISTING_QA_PAIRS,
) -> SubstantiveChangeItem:
    """Promote existing on-page Q&A into an FAQ block, or needs_author_input."""
    lower = (source_markdown or "").lower()
    if "faq" in lower or "frequently asked" in lower:
        return SubstantiveChangeItem(
            content_gap="FAQ section already present",
            proposed_action="add_faq_from_existing_qa",
            reason="FAQ already present; no duplicate promote.",
            expected_aeo_benefit=_benefit("add_faq_from_existing_qa"),
            op_kind="add_faq_from_existing_qa",
            disposition="deferred",
            related_gap_ids=list(related_gap_ids or []),
            related_query_ids=list(related_query_ids or []),
            target="section:FAQ",
            target_kind="faq",
            action="add",
            apply_mode="unsupported",
            status="unsupported",
        )

    pairs = extract_existing_qa_pairs(source_markdown)
    if len(pairs) < min_pairs:
        return SubstantiveChangeItem(
            content_gap=(
                f"Fewer than {min_pairs} existing on-page question/answer pairs "
                f"(found {len(pairs)}); cannot assemble FAQ without inventing Q/A"
            ),
            evidence=[],
            proposed_action="author_input_required",
            proposed_content=None,
            reason=(
                "add_faq_from_existing_qa requires existing on-page question headings "
                "with answer paragraphs; author input required — never invent Q or A."
            ),
            expected_aeo_benefit=_benefit("author_input_required"),
            op_kind="add_faq_from_existing_qa",
            disposition="author_input_required",
            related_gap_ids=list(related_gap_ids or []),
            related_query_ids=list(related_query_ids or []),
            target="section:FAQ",
            target_kind="faq",
            action="add",
            apply_mode="author_input_required",
            status="needs_author_input",
        )

    proposed = assemble_faq_block(pairs)
    evidence = [f"Q: {q} | A: {a}" for q, a in pairs[:min_pairs]]
    return SubstantiveChangeItem(
        content_gap="On-page Q&A exists but is not assembled as an FAQ section",
        evidence=evidence,
        proposed_action="add_faq_from_existing_qa",
        proposed_content=proposed.strip(),
        reason="Assemble FAQ from existing on-page question headings and answers.",
        expected_aeo_benefit=_benefit("add_faq_from_existing_qa"),
        op_kind="add_faq_from_existing_qa",
        disposition="actionable",
        related_gap_ids=list(related_gap_ids or []),
        related_query_ids=list(related_query_ids or []),
        target="section:FAQ",
        target_kind="faq",
        action="add",
        original=None,
        apply_mode="insert_after",
        status="ready",
    )


def propose_howto_from_existing_steps(
    *,
    source_markdown: str,
    related_gap_ids: list[str] | None = None,
    related_query_ids: list[str] | None = None,
    min_steps: int = HOWTO_MIN_EXISTING_STEPS,
) -> SubstantiveChangeItem:
    """Promote existing numbered steps into a Steps section, or needs_author_input."""
    lower = (source_markdown or "").lower()
    if "step-by-step" in lower or re.search(
        r"^##\s+steps\b", source_markdown or "", re.I | re.M
    ):
        return SubstantiveChangeItem(
            content_gap="Steps section already present",
            proposed_action="add_howto_from_existing_steps",
            reason="Steps section already present; no duplicate promote.",
            expected_aeo_benefit=_benefit("add_howto_from_existing_steps"),
            op_kind="add_howto_from_existing_steps",
            disposition="deferred",
            related_gap_ids=list(related_gap_ids or []),
            related_query_ids=list(related_query_ids or []),
            target="section:Steps",
            target_kind="howto",
            action="add",
            apply_mode="unsupported",
            status="unsupported",
        )

    steps = extract_existing_steps(source_markdown)
    if len(steps) < min_steps:
        return SubstantiveChangeItem(
            content_gap=(
                f"Fewer than {min_steps} existing numbered/Step-N lines "
                f"(found {len(steps)}); cannot assemble HowTo without inventing steps"
            ),
            evidence=[],
            proposed_action="author_input_required",
            proposed_content=None,
            reason=(
                "add_howto_from_existing_steps requires ≥3 existing numbered steps "
                "or 'Step N:' lines; author input required — never invent steps."
            ),
            expected_aeo_benefit=_benefit("author_input_required"),
            op_kind="add_howto_from_existing_steps",
            disposition="author_input_required",
            related_gap_ids=list(related_gap_ids or []),
            related_query_ids=list(related_query_ids or []),
            target="section:Steps",
            target_kind="howto",
            action="add",
            apply_mode="author_input_required",
            status="needs_author_input",
        )

    # If body already has a full numbered list (≥3), leave unchanged (idempotent).
    if len(extract_existing_steps(source_markdown)) >= min_steps and re.search(
        r"^##\s+steps\b", source_markdown or "", re.I | re.M
    ):
        return SubstantiveChangeItem(
            content_gap="Steps already structured",
            proposed_action="add_howto_from_existing_steps",
            reason="Steps already structured.",
            op_kind="add_howto_from_existing_steps",
            disposition="deferred",
            target="section:Steps",
            target_kind="howto",
            action="add",
            apply_mode="unsupported",
            status="unsupported",
            related_gap_ids=list(related_gap_ids or []),
            related_query_ids=list(related_query_ids or []),
        )

    proposed = assemble_howto_block(steps)
    if proposed.strip() in (source_markdown or ""):
        return SubstantiveChangeItem(
            content_gap="Steps block already present verbatim",
            proposed_action="add_howto_from_existing_steps",
            reason="Assembled Steps block already present.",
            op_kind="add_howto_from_existing_steps",
            disposition="deferred",
            target="section:Steps",
            target_kind="howto",
            action="add",
            apply_mode="unsupported",
            status="unsupported",
            related_gap_ids=list(related_gap_ids or []),
            related_query_ids=list(related_query_ids or []),
        )

    return SubstantiveChangeItem(
        content_gap="On-page steps exist but are not assembled as a Steps section",
        evidence=list(steps[:min_steps]),
        proposed_action="add_howto_from_existing_steps",
        proposed_content=proposed.strip(),
        reason="Assemble Steps section from existing numbered / Step-N lines.",
        expected_aeo_benefit=_benefit("add_howto_from_existing_steps"),
        op_kind="add_howto_from_existing_steps",
        disposition="actionable",
        related_gap_ids=list(related_gap_ids or []),
        related_query_ids=list(related_query_ids or []),
        target="section:Steps",
        target_kind="howto",
        action="add",
        apply_mode="insert_after",
        status="ready",
    )


def propose_seo_description_op(
    *,
    brief: dict[str, Any] | None = None,
    page_intelligence: dict[str, Any] | None = None,
    related_gap_ids: list[str] | None = None,
) -> SubstantiveChangeItem | None:
    """Metadata-only SEO description transport when brief/page intel has text."""
    brief = brief or {}
    pi = page_intelligence or {}
    text = ""
    if isinstance(brief.get("proposed_meta_description"), str):
        text = brief["proposed_meta_description"].strip()
    if not text and isinstance(pi.get("meta_description"), str):
        text = str(pi.get("meta_description") or "").strip()
    if not text:
        return SubstantiveChangeItem(
            content_gap="No SEO description available from brief or page intel",
            proposed_action="author_input_required",
            reason="metadata.seo_description needs brief/page text; author input required.",
            expected_aeo_benefit=_benefit("author_input_required"),
            op_kind="metadata_seo_description",
            disposition="author_input_required",
            related_gap_ids=list(related_gap_ids or []),
            target="meta_description",
            target_kind="meta_description",
            action="add",
            apply_mode="author_input_required",
            status="needs_author_input",
        )
    return SubstantiveChangeItem(
        content_gap="SEO description should be available in Hashnode settings",
        evidence=[text[:200]],
        proposed_action="metadata_seo_description",
        proposed_content=text,
        reason="Transport SEO description as Hashnode metadata only (body unchanged).",
        expected_aeo_benefit=_benefit("metadata_seo_description"),
        op_kind="metadata_seo_description",
        disposition="actionable",
        related_gap_ids=list(related_gap_ids or []),
        target="meta_description",
        target_kind="meta_description",
        action="add",
        apply_mode="metadata_only",
        status="ready",
    )


def _author_input_for_deferred(
    *,
    gap: dict[str, Any],
    query_text: str | None,
    reason: str,
    op_kind: str = "author_input_required",
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
        op_kind=op_kind,
        disposition="author_input_required",
        related_gap_ids=[gid] if gid else [],
        related_query_ids=qids,
        target="body",
        target_kind="body",
        action="rewrite",
        query_text=query_text,
        apply_mode="author_input_required",
        status="needs_author_input",
    )


def build_substantive_change_plan(
    *,
    source_markdown: str,
    gaps: list[Any] | None = None,
    coverage_by_query: list[dict[str, Any]] | None = None,
    page_intelligence: dict[str, Any] | None = None,
    existing_ops: list[dict[str, Any]] | None = None,
    h1: str | None = None,
    brief: dict[str, Any] | None = None,
    draft_paid: bool = False,
    llm_api_key: str | None = None,
    llm_model: str | None = None,
    llm_base_url: str | None = None,
    grounded_client: OpenAICompatibleChat | None = None,
) -> SubstantiveChangePlan:
    """Diagnose MVP change plan: intro / SEO / FAQ / HowTo + grounded section ops.

    Never forces a fixed number of edits. Grounded LLM body ops require
    ``draft_paid`` + API key (or an injected ``grounded_client``). Deferred
    kinds → needs_author_input / research_required. Prefer ≤2 grounded body ops.
    """
    warnings: list[str] = []
    items: list[SubstantiveChangeItem] = []
    pi = page_intelligence or {}
    gap_rows = _gap_dicts(gaps)
    coverage = list(coverage_by_query or [])
    resolved_h1 = h1 or str(pi.get("h1") or pi.get("title") or "").strip() or None
    if not resolved_h1:
        m = re.search(r"^#\s+(.+)$", source_markdown or "", re.M)
        if m:
            resolved_h1 = m.group(1).strip()

    # Resolve grounded synth client (fail closed when draft_paid=false / no key).
    synth_client = grounded_client
    if synth_client is None and draft_paid and (llm_api_key or "").strip():
        from aeo_mvp.content.grounded_synth import resolve_openai_compatible_client

        synth_client = resolve_openai_compatible_client(
            draft_paid=True,
            api_key=llm_api_key,
            model=llm_model,
            base_url=llm_base_url,
        )

    # --- 1) rewrite_introduction (PR #44) ---
    needs_intro = False
    intro_gap_ids: list[str] = []
    intro_query_ids: list[str] = []
    ans = pi.get("answerability_signals") or pi.get("answerability") or {}
    for g in gap_rows:
        gt = str(g.get("gap_type") or "").lower()
        kind = str(g.get("kind") or "").lower()
        # FAQ / HowTo gaps are handled by promote-only paths — not intro.
        if kind in {"missing_faq", "missing_steps"}:
            continue
        if (
            "answer_first" in str(g.get("gap_id") or "")
            or kind in {"missing_answer", "no_answer_first"}
            or gt == "evidence_gap"
            or ("answer" in gt and "faq" not in gt)
        ):
            needs_intro = True
            gid = str(g.get("gap_id") or g.get("id") or "")
            if gid:
                intro_gap_ids.append(gid)
            if g.get("query_id"):
                intro_query_ids.append(str(g["query_id"]))
    if isinstance(ans, dict) and ans.get("answer_first_heuristic") is False:
        needs_intro = True
    if "no_answer_first" in (pi.get("limits") or []):
        needs_intro = True
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

    if needs_intro and (source_markdown or "").strip():
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
                    target_kind="introduction",
                    action="rewrite",
                    original=proposal.original,
                    apply_mode="replace_region",
                    status="ready",
                )
            )
        else:
            warnings.append("intro_rewrite_no_grounded_proposal")
            items.append(
                SubstantiveChangeItem(
                    content_gap="Introduction rewrite requested but not groundable",
                    proposed_action="author_input_required",
                    reason=(
                        "No grounded introduction rewrite from on-page evidence; "
                        "author input required — never invent or reorder-only."
                    ),
                    expected_aeo_benefit=_benefit("author_input_required"),
                    op_kind="rewrite_introduction",
                    disposition="author_input_required",
                    related_gap_ids=list(dict.fromkeys(intro_gap_ids)),
                    related_query_ids=list(dict.fromkeys(intro_query_ids)),
                    target="introduction",
                    target_kind="introduction",
                    action="rewrite",
                    apply_mode="author_input_required",
                    status="needs_author_input",
                )
            )

    # --- 2) metadata.seo_description ---
    wants_meta = any(
        str(op.get("target") or op.get("target_locator") or "").lower()
        in {"meta_description", "seo_description", "seo description"}
        for op in (existing_ops or [])
        if isinstance(op, dict)
    ) or any(
        str(g.get("gap_type") or "").lower() in {"schema_gap", "metadata"}
        or "meta" in str(g.get("kind") or "").lower()
        for g in gap_rows
    )
    if wants_meta or brief or pi.get("meta_description"):
        meta_gaps = [
            str(g.get("gap_id") or g.get("id") or "")
            for g in gap_rows
            if str(g.get("gap_type") or "").lower() in {"schema_gap", "metadata"}
        ]
        meta_item = propose_seo_description_op(
            brief=brief,
            page_intelligence=pi,
            related_gap_ids=[g for g in meta_gaps if g][:2],
        )
        if meta_item is not None and (
            wants_meta or meta_item.status == "ready"
        ):
            # Only emit when requested via ops/gaps, or when ready text exists
            # and a meta op/gap is present. Avoid forcing SEO edits.
            if wants_meta or (
                meta_item.status == "ready"
                and any(
                    str(op.get("target") or op.get("target_locator") or "").lower()
                    in {"meta_description", "seo_description"}
                    for op in (existing_ops or [])
                    if isinstance(op, dict)
                )
            ):
                items.append(meta_item)

    # --- 3) add_faq_from_existing_qa ---
    wants_faq = any(
        "faq" in str(g.get("gap_type") or "").lower()
        or str(g.get("kind") or "") == "missing_faq"
        or "question" in str(g.get("gap_type") or "").lower()
        for g in gap_rows
    )
    faq_gap_ids = [
        str(g.get("gap_id") or g.get("id") or "")
        for g in gap_rows
        if "faq" in str(g.get("gap_type") or "").lower()
        or str(g.get("kind") or "") == "missing_faq"
        or "question" in str(g.get("gap_type") or "").lower()
    ]
    faq_qids: list[str] = []
    for g in gap_rows:
        if str(g.get("gap_id") or g.get("id") or "") in faq_gap_ids:
            faq_qids.extend(str(x) for x in (g.get("query_ids") or []))
            if g.get("query_id"):
                faq_qids.append(str(g["query_id"]))
    if wants_faq:
        items.append(
            propose_faq_from_existing_qa(
                source_markdown=source_markdown,
                related_gap_ids=[g for g in faq_gap_ids if g],
                related_query_ids=list(dict.fromkeys(faq_qids)),
            )
        )

    # --- 4) add_howto_from_existing_steps ---
    wants_howto = any(
        "howto" in str(g.get("gap_type") or "").lower()
        or str(g.get("kind") or "") in {"missing_steps"}
        or "step" in str(g.get("kind") or "").lower()
        for g in gap_rows
    )
    howto_gap_ids = [
        str(g.get("gap_id") or g.get("id") or "")
        for g in gap_rows
        if "howto" in str(g.get("gap_type") or "").lower()
        or str(g.get("kind") or "") in {"missing_steps"}
        or "step" in str(g.get("kind") or "").lower()
    ]
    howto_qids: list[str] = []
    for g in gap_rows:
        if str(g.get("gap_id") or g.get("id") or "") in howto_gap_ids:
            howto_qids.extend(str(x) for x in (g.get("query_ids") or []))
            if g.get("query_id"):
                howto_qids.append(str(g["query_id"]))
    if wants_howto:
        items.append(
            propose_howto_from_existing_steps(
                source_markdown=source_markdown,
                related_gap_ids=[g for g in howto_gap_ids if g],
                related_query_ids=list(dict.fromkeys(howto_qids)),
            )
        )

    # --- 5) Grounded rewrite_section / add_explanation (≤ MAX_GROUNDED_BODY_OPS)
    # Secondary promote kinds already handled above. Prefer strong section ops.
    covered_gap_ids = {
        gid for it in items for gid in (it.related_gap_ids or []) if gid
    }
    grounded_budget = MAX_GROUNDED_BODY_OPS
    for g in gap_rows:
        gid = str(g.get("gap_id") or g.get("id") or "")
        if gid and gid in covered_gap_ids:
            continue
        gt = str(g.get("gap_type") or "").lower()
        kind = str(g.get("kind") or "").lower()
        qtext = _query_text_for_gap(g, coverage)
        # Schema / JSON-LD invent, cross-page, freshness, entity, cite — never synth
        if gt in {
            "schema_gap",
            "false_coverage_nav",
            "genre_mismatch",
            "freshness_gap",
            "entity_mismatch",
            "cite_miss",
            "technical_extractability_gap",
        } or kind in {"entity_unclear", "outdated_claim", "unsupported_claim"}:
            items.append(
                _author_input_for_deferred(
                    gap=g,
                    query_text=qtext,
                    reason=(
                        f"Deferred/non-MVP gap_type={gt or kind}: no automatic invent "
                        "(schema/JSON-LD, cross-page URLs, freshness/entity/cite). "
                        "Author input required."
                    ),
                    op_kind="author_input_required",
                )
            )
            continue
        # Thin/absent coverage → attempt grounded section synth when opted in.
        if g.get("page_coverage") in {"absent", "thin", "mismatched"} or gt in {
            "thin_coverage",
            "missing_page",
            "question_coverage_gap",
            "evidence_gap",
            "structure_gap",
        }:
            if not (g.get("query_id") or g.get("query_ids") or qtext):
                continue
            # Intro gaps already handled by rewrite_introduction — skip duplicate.
            if kind in {"missing_answer", "no_answer_first"} or (
                gid and "answer_first" in gid
            ):
                if any(
                    it.op_kind == "rewrite_introduction" for it in items
                ):
                    continue
            qids = [str(x) for x in (g.get("query_ids") or [])]
            if g.get("query_id"):
                qids.append(str(g["query_id"]))
            qids = list(dict.fromkeys(qids))
            gap_ids = [gid] if gid else []

            if grounded_budget <= 0 or synth_client is None:
                items.append(
                    _author_input_for_deferred(
                        gap=g,
                        query_text=qtext,
                        reason=(
                            "rewrite_section / add_explanation require draft_paid + "
                            "API key (fail closed) or grounded budget exhausted; "
                            "author input required — never invent content."
                            if synth_client is None
                            else (
                                "Grounded body-op budget exhausted (prefer 1–2 strong "
                                "section ops); author input required — never invent."
                            )
                        ),
                        op_kind="rewrite_section",
                    )
                )
                continue

            picked = select_section_for_query(
                source_markdown,
                query_text=qtext or "",
                h1=resolved_h1,
            )
            if picked is None:
                # No safe rewrite span → try add_explanation on first H2, else research.
                from aeo_mvp.content.grounded_synth import list_section_bodies

                sections = list_section_bodies(source_markdown)
                anchor = None
                for heading, _body, _lvl in sections:
                    if resolved_h1 and heading.strip().lower() == resolved_h1.lower():
                        continue
                    anchor = heading
                    break
                if anchor is None:
                    items.append(
                        SubstantiveChangeItem(
                            content_gap=str(
                                g.get("rationale")
                                or g.get("explanation")
                                or "Insufficient on-page section corpus"
                            ),
                            proposed_action="research_required",
                            reason=(
                                "Corpus insufficient for rewrite_section / "
                                "add_explanation (research_required); never invent."
                            ),
                            expected_aeo_benefit=_benefit("author_input_required"),
                            op_kind="rewrite_section",
                            disposition="research_required",
                            related_gap_ids=gap_ids,
                            related_query_ids=qids,
                            target="section:unknown",
                            target_kind="section",
                            action="rewrite",
                            query_text=qtext,
                            apply_mode="author_input_required",
                            status="needs_author_input",
                        )
                    )
                    continue
                result = synthesize_add_explanation(
                    client=synth_client,
                    source_markdown=source_markdown,
                    query_text=qtext or "",
                    anchor_heading=anchor,
                    h1=resolved_h1,
                    related_gap_ids=gap_ids,
                    related_query_ids=qids,
                )
            else:
                heading, body = picked
                result = synthesize_rewrite_section(
                    client=synth_client,
                    source_markdown=source_markdown,
                    query_text=qtext or "",
                    h1=resolved_h1,
                    related_gap_ids=gap_ids,
                    related_query_ids=qids,
                    section_heading=heading,
                    section_body=body,
                )
                # If rewrite blocked but page has evidence, try add_explanation once.
                if (
                    result.disposition != "actionable"
                    and result.disposition != "research_required"
                ):
                    alt = synthesize_add_explanation(
                        client=synth_client,
                        source_markdown=source_markdown,
                        query_text=qtext or "",
                        anchor_heading=heading,
                        h1=resolved_h1,
                        related_gap_ids=gap_ids,
                        related_query_ids=qids,
                    )
                    if alt.disposition == "actionable":
                        result = alt

            warnings.extend(result.warnings)
            items.append(
                SubstantiveChangeItem(
                    content_gap=str(
                        g.get("rationale")
                        or g.get("explanation")
                        or f"Thin coverage for query: {qtext or gid}"
                    ),
                    evidence=list(result.evidence),
                    proposed_action=str(result.op_kind),
                    proposed_content=result.proposed,
                    reason=result.reason,
                    expected_aeo_benefit=_benefit(str(result.op_kind)),
                    op_kind=result.op_kind,  # type: ignore[arg-type]
                    disposition=result.disposition,  # type: ignore[arg-type]
                    related_gap_ids=list(result.related_gap_ids or gap_ids),
                    related_query_ids=list(result.related_query_ids or qids),
                    target=result.target,
                    target_kind=result.target_kind,
                    action=result.action,
                    original=result.original,
                    query_text=result.query_text or qtext,
                    apply_mode=result.apply_mode  # type: ignore[arg-type]
                    if result.disposition == "actionable"
                    else "author_input_required",
                    status=result.status,  # type: ignore[arg-type]
                    claims=[c.to_dict() for c in result.claims],
                    llm_used=result.llm_used,
                )
            )
            if result.disposition == "actionable":
                grounded_budget -= 1
                if gid:
                    covered_gap_ids.add(gid)

    # Deduplicate: prefer ready over needs_author_input for same op_kind+target
    deduped: list[SubstantiveChangeItem] = []
    seen: set[str] = set()
    for it in items:
        if it.status == "ready":
            key = f"ready|{it.op_kind}|{it.target.lower()}"
            if key in seen:
                continue
            seen.add(key)
            deduped.append(it)
    for it in items:
        if it.status == "ready":
            continue
        key = f"{it.status}|{it.op_kind}|{it.target.lower()}|{(it.content_gap or '')[:40]}"
        if key in seen:
            continue
        # Do not drop FAQ/HowTo/SEO/intro/section author_input just because
        # another ready op cites other gaps.
        if it.op_kind not in {
            "add_faq_from_existing_qa",
            "add_howto_from_existing_steps",
            "metadata_seo_description",
            "rewrite_introduction",
            "rewrite_section",
            "add_explanation",
        }:
            if it.related_gap_ids and any(
                gid in (a.related_gap_ids or [])
                for a in deduped
                if a.status == "ready"
                for gid in it.related_gap_ids
            ):
                continue
        seen.add(key)
        deduped.append(it)

    return SubstantiveChangePlan(items=deduped, warnings=warnings)


def annotate_gaps_with_disposition(
    gaps: list[dict[str, Any]],
    plan: SubstantiveChangePlan,
) -> list[dict[str, Any]]:
    by_gap: dict[str, SubstantiveChangeItem] = {}
    for it in plan.items:
        for gid in it.related_gap_ids:
            prev = by_gap.get(gid)
            if prev is None or (
                prev.status != "ready" and it.status == "ready"
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
            row["op_status"] = it.status
            row["apply_mode"] = it.apply_mode
        out.append(row)
    return out


def merge_plan_into_ops(
    ops: list[dict[str, Any]],
    plan: SubstantiveChangePlan,
) -> list[dict[str, Any]]:
    """Merge MVP plan items onto edit ops; append new ready / author_input ops."""
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
        payload = it.to_edit_op_dict()
        if it.status != "ready" or not it.proposed_content:
            if it.status == "needs_author_input":
                k = it.target.lower()
                if k in by_target:
                    by_target[k]["disposition"] = it.disposition
                    by_target[k]["status"] = "needs_author_input"
                    by_target[k]["apply_mode"] = "author_input_required"
                    by_target[k]["op_kind"] = it.op_kind
                    by_target[k]["proposed"] = None
                    by_target[k]["claims"] = list(it.claims)
                    by_target[k]["reason"] = it.reason
                elif not any(
                    str(op.get("op_kind") or "") == str(it.op_kind)
                    and op.get("status") == "needs_author_input"
                    for op in enriched
                ):
                    enriched.append(payload)
            continue

        keys_to_try = [it.target.lower()]
        if it.op_kind == "rewrite_introduction":
            keys_to_try.extend(["introduction", "intro", "opening"])
        if it.op_kind == "metadata_seo_description":
            keys_to_try.extend(["meta_description", "seo_description"])

        matched = None
        for k in keys_to_try:
            if k in by_target:
                matched = by_target[k]
                break
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
            matched["claims"] = list(it.claims)
            matched["op_kind"] = it.op_kind
            matched["disposition"] = (
                "actionable"
                if it.status == "ready"
                else it.disposition
            )
            matched["status"] = it.status
            matched["apply_mode"] = it.apply_mode
            matched["target_kind"] = it.target_kind
            matched["expected_aeo_benefit"] = it.expected_aeo_benefit
            matched["llm_used"] = it.llm_used
            if it.reason and not matched.get("reason"):
                matched["reason"] = it.reason
            if it.related_gap_ids and not matched.get("related_gap_ids"):
                matched["related_gap_ids"] = list(it.related_gap_ids)
            if it.related_query_ids and not matched.get("related_query_ids"):
                matched["related_query_ids"] = list(it.related_query_ids)
        else:
            enriched.append(payload)
            by_target[it.target.lower()] = payload

    return enriched
