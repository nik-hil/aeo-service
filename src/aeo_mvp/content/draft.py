"""opt-draft-v1 — DraftGenerator Protocol; Null / skeleton default; paid=false."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

from aeo_mvp.content.models import (
    DRAFT_VERSION,
    ContentChange,
    ContentGapReport,
    ContentOptimizationBrief,
    EditOp,
    OptimizedContentDraft,
    PageIntelligence,
    UnsupportedClaim,
    UnsupportedClaimWarning,
)


@dataclass
class GeneratorResult:
    title: str | None
    meta_description: str | None
    body_markdown: str
    faq: list[dict[str, str]] = field(default_factory=list)
    schema_jsonld: list[dict[str, Any]] = field(default_factory=list)
    unsupported_claims: list[UnsupportedClaim] = field(default_factory=list)
    writer: str = "null_v1"
    llm_used: bool = False
    paid_llm: bool = False
    warnings: list[str] = field(default_factory=list)


class DraftGenerator(Protocol):
    """LLM/draft behind interface only. Must not call paid APIs unless opted in."""

    def generate(
        self,
        page: PageIntelligence,
        brief: ContentOptimizationBrief,
        *,
        source_excerpts: list[str] | None = None,
    ) -> GeneratorResult: ...


class NullDraftGenerator:
    """Default: no LLM, paid=false. Emits empty body + warnings from brief gaps."""

    name = "null"

    def generate(
        self,
        page: PageIntelligence,
        brief: ContentOptimizationBrief,
        *,
        source_excerpts: list[str] | None = None,
    ) -> GeneratorResult:
        _ = source_excerpts
        claims = [
            UnsupportedClaim(
                claim="draft_not_generated",
                support="unsupported",
                reason="NullDraftGenerator: content_draft=false / generate_draft=false",
                provenance="generated",
            )
        ]
        return GeneratorResult(
            title=brief.proposed_title or page.title,
            meta_description=brief.proposed_meta_description,
            body_markdown="",
            faq=[],
            schema_jsonld=[],
            unsupported_claims=claims,
            writer=self.name,
            llm_used=False,
            paid_llm=False,
            warnings=["null_draft:skipped_paid_false"],
        )


class DeterministicSkeletonDraftGenerator:
    """Deterministic skeleton from brief + observed page signals. Never paid/LLM."""

    name = "deterministic_skeleton"

    def generate(
        self,
        page: PageIntelligence,
        brief: ContentOptimizationBrief,
        *,
        source_excerpts: list[str] | None = None,
    ) -> GeneratorResult:
        warnings: list[str] = []
        claims: list[UnsupportedClaim] = []
        excerpts = source_excerpts or []

        lines: list[str] = []
        title = brief.proposed_title or page.title or page.h1 or "Untitled"
        h1 = brief.proposed_h1 or page.h1 or title
        lines.append(f"# {h1}")
        lines.append("")
        lead = page.meta_description or (
            f"{h1} — grounded skeleton from existing page signals."
        )
        lines.append(lead)
        lines.append("")

        if excerpts:
            lines.append("## Source anchors")
            lines.append("")
            for ex in excerpts[:5]:
                lines.append(f"> {ex[:280]}")
                lines.append("")
        else:
            for h in page.headings[:4]:
                lines.append(f"## {h.text}")
                lines.append("")
                lines.append(
                    f"Retain and clarify the existing '{h.text}' section using only "
                    "verified on-page facts. Do not invent statistics or citations."
                )
                lines.append("")

        sections = list(getattr(brief, "outline_sections", None) or [])
        if not sections:
            from aeo_mvp.content.models import OutlineSection

            for h in brief.outline or []:
                if isinstance(h, str):
                    sections.append(
                        OutlineSection(heading=h, level=2, retain_improve_add="add")
                    )
                elif hasattr(h, "heading"):
                    sections.append(h)
        for section in sections:
            if section.level == 1:
                continue
            if section.retain_improve_add == "retain" and any(
                h.text == section.heading for h in page.headings
            ):
                continue
            lines.append(f"{'#' * section.level} {section.heading}")
            lines.append("")
            placeholder = (
                f"*(Skeleton)* Directly answer: {section.heading}. "
                "Use site-owned facts only; leave [NEEDS_SOURCE] where evidence is missing."
            )
            lines.append(placeholder)
            lines.append("")
            claims.append(
                UnsupportedClaim(
                    claim=f"section:{section.heading}",
                    support="unsupported",
                    reason="Skeleton placeholder requires sourced evidence before publish",
                    provenance="generated",
                )
            )

        faq: list[dict[str, str]] = []
        for item in brief.faq_suggestions:
            q = item.get("question") or ""
            answer = (
                f"{q.rstrip('?')} is addressed on this page in the related section. "
                "[NEEDS_SOURCE] Expand with verified details only."
            )
            faq.append({"question": q, "answer": answer})
            claims.append(
                UnsupportedClaim(
                    claim=f"faq:{q}",
                    support="unsupported",
                    reason="FAQ skeleton contains NEEDS_SOURCE",
                    provenance="generated",
                )
            )

        schema: list[dict[str, Any]] = []
        for t in brief.schema_suggestions:
            if t == "FAQPage" and faq:
                schema.append(
                    {
                        "@context": "https://schema.org",
                        "@type": "FAQPage",
                        "mainEntity": [
                            {
                                "@type": "Question",
                                "name": f["question"],
                                "acceptedAnswer": {"@type": "Answer", "text": f["answer"]},
                            }
                            for f in faq
                        ],
                    }
                )
            elif t in ("Article", "BlogPosting"):
                schema.append(
                    {
                        "@context": "https://schema.org",
                        "@type": t,
                        "headline": title,
                        "description": brief.proposed_meta_description,
                    }
                )
            else:
                schema.append({"@context": "https://schema.org", "@type": t, "name": title})

        body = "\n".join(lines)
        for banned in ("% of users", "studies show", "guaranteed citation"):
            if banned in body.lower():
                claims.append(
                    UnsupportedClaim(
                        claim=banned,
                        support="unsupported",
                        reason="Banned ungrounded marketing pattern",
                        provenance="generated",
                    )
                )

        # Optimizer rule: unsupported_claims[] required on drafts
        if not claims:
            claims.append(
                UnsupportedClaim(
                    claim="skeleton_ungrounded",
                    support="unsupported",
                    reason=(
                        "Deterministic skeleton is generated — verify all claims "
                        "against observed page evidence before publish"
                    ),
                    provenance="generated",
                )
            )

        return GeneratorResult(
            title=title,
            meta_description=brief.proposed_meta_description,
            body_markdown=body.strip() + "\n",
            faq=faq,
            schema_jsonld=schema,
            unsupported_claims=claims,
            writer=self.name,
            llm_used=False,
            paid_llm=False,
            warnings=warnings,
        )


class PaidLLMDraftGenerator:
    """Opt-in stub — refuses live calls. Never used by default."""

    name = "paid_llm_stub_v0"

    def __init__(
        self,
        *,
        draft_paid: bool = False,
        api_key: str | None = None,
        model: str | None = None,
    ) -> None:
        self.draft_paid = draft_paid
        self.api_key = api_key
        self.model = model or "unset"

    def generate(
        self,
        page: PageIntelligence,
        brief: ContentOptimizationBrief,
        *,
        source_excerpts: list[str] | None = None,
    ) -> GeneratorResult:
        if not self.draft_paid or not self.api_key:
            fallback = DeterministicSkeletonDraftGenerator().generate(
                page, brief, source_excerpts=source_excerpts
            )
            fallback.warnings = list(fallback.warnings) + [
                "paid_llm_skipped:opt_in_or_key_missing"
            ]
            fallback.writer = f"{self.name}+skeleton_fallback"
            fallback.paid_llm = False
            fallback.llm_used = False
            return fallback
        raise RuntimeError(
            "Paid LLM draft generator is not implemented; refusing external API calls."
        )


def resolve_draft_generator(
    *,
    generate_draft: bool = False,
    draft_paid: bool = False,
    content_draft: bool | None = None,
    content_draft_provider: str | None = None,
    api_key: str | None = None,
    model: str | None = None,
) -> DraftGenerator:
    """Resolve draft writer (AUTHORITATIVE sheet).

    - ``content_draft=false`` / ``generate_draft=false`` → ``NullDraftGenerator``
      (status skipped_paid_false).
    - ``content_draft=true`` + provider null/skeleton → ``DeterministicSkeletonDraftGenerator``.
    - paid provider + key → paid stub (refuses live calls in MVP).
    """
    want_draft = bool(generate_draft if content_draft is None else content_draft)
    provider = (content_draft_provider or "").strip().lower() or None
    if draft_paid and api_key and provider in (None, "openai_compatible", "paid"):
        return PaidLLMDraftGenerator(draft_paid=True, api_key=api_key, model=model)
    if want_draft:
        return DeterministicSkeletonDraftGenerator()
    return NullDraftGenerator()


def build_optimized_draft(
    page: PageIntelligence,
    brief: ContentOptimizationBrief,
    gap_report: ContentGapReport,
    *,
    generator: DraftGenerator | None = None,
    source_excerpts: list[str] | None = None,
) -> OptimizedContentDraft:
    """Build opt-draft-v1. content_provenance=generated — never observed."""
    _ = gap_report
    gen = generator or NullDraftGenerator()
    result = gen.generate(page, brief, source_excerpts=source_excerpts)

    raw_ops = list(brief.edit_ops) or [
        c.to_edit_op(idx=i) for i, c in enumerate(brief.legacy_edit_ops)
    ]
    change_plan: list[ContentChange] = list(brief.legacy_edit_ops) or [
        ContentChange(
            action=e.action,
            target=e.target_locator or e.anchor_locator or e.op_id,
            reason=e.instruction,
        )
        for e in raw_ops
        if isinstance(e, EditOp)
    ]
    change_summary = [f"{c.action}: {c.target} — {c.reason}" for c in change_plan]
    if not change_summary:
        for e in raw_ops:
            if isinstance(e, EditOp):
                change_summary.append(
                    f"{e.action}: {e.target_locator or e.anchor_locator} — {e.instruction}"
                )

    warnings_list: list[UnsupportedClaimWarning] = []
    for i, u in enumerate(result.unsupported_claims):
        if isinstance(u, UnsupportedClaimWarning):
            warnings_list.append(u)
        else:
            warnings_list.append(u.to_warning(idx=i))
    warnings_from_claims = [
        f"{u.support}:{u.claim_text} — {u.reason}" for u in warnings_list
    ]

    is_null = isinstance(gen, NullDraftGenerator) or result.writer in ("null", "null_v1")
    status = (
        "skipped_paid_false"
        if is_null and not (result.body_markdown or "").strip()
        else "generated"
    )

    writer = "null" if result.writer in ("null", "null_v1") else result.writer
    return OptimizedContentDraft(
        draft_version=DRAFT_VERSION,
        schema_version=DRAFT_VERSION,
        brief_id=brief.brief_id,
        status=status,  # type: ignore[arg-type]
        generator=writer,
        paid=bool(result.paid_llm),
        title=result.title,
        body_markdown=result.body_markdown if result.body_markdown is not None else "",
        disclaimer=(
            "Draft suggestion only — not published; not a guarantee of AI citation."
        ),
        unsupported_claims=warnings_list,
        warnings=list(result.warnings),
        page_url=page.url,
        meta_description=result.meta_description,
        faq=result.faq,
        schema_jsonld=result.schema_jsonld,
        internal_links=list(brief.internal_link_suggestions),
        change_summary=change_summary,
        change_plan=change_plan,
        unsupported_claim_warnings=warnings_from_claims,
        writer=writer,
        llm_used=result.llm_used,
        paid_llm=result.paid_llm,
        content_provenance="generated",
        method=f"{DRAFT_VERSION}+{writer}",
    )
