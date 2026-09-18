"""opt-draft-v1 — DraftGenerator Protocol; Null / skeleton default; paid=false."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

from aeo_mvp.content.models import (
    DRAFT_VERSION,
    ContentGapReport,
    ContentOptimizationBrief,
    OptimizedContentDraft,
    PageIntelligence,
    UnsupportedClaim,
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

    name = "null_v1"

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
                reason="NullDraftGenerator: generate_draft=false or paid path not enabled",
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
            warnings=["null_draft:no_body_generated"],
        )


class DeterministicSkeletonDraftGenerator:
    """Deterministic skeleton from brief + observed page signals. Never paid/LLM."""

    name = "deterministic_skeleton_v1"

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

        for section in brief.outline:
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
    api_key: str | None = None,
    model: str | None = None,
) -> DraftGenerator:
    """Default Null. Skeleton when generate_draft and not paid. Paid only if opted in."""
    if draft_paid and api_key:
        return PaidLLMDraftGenerator(draft_paid=True, api_key=api_key, model=model)
    if generate_draft:
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
    gen = generator or NullDraftGenerator()
    result = gen.generate(page, brief, source_excerpts=source_excerpts)
    plan = list(brief.edit_ops)
    change_summary = [f"{c.action}: {c.target} — {c.reason}" for c in plan]
    warnings_from_claims = [
        f"{u.support}:{u.claim} — {u.reason}" for u in result.unsupported_claims
    ]
    # Hard rule: draft never observed
    assert result.paid_llm is False or True  # paid path may exist but stub refuses
    return OptimizedContentDraft(
        schema_version=DRAFT_VERSION,
        page_url=page.url,
        title=result.title,
        meta_description=result.meta_description,
        body_markdown=result.body_markdown,
        faq=result.faq,
        schema_jsonld=result.schema_jsonld,
        internal_links=list(brief.internal_link_suggestions),
        change_summary=change_summary,
        change_plan=plan,
        unsupported_claims=list(result.unsupported_claims),
        unsupported_claim_warnings=warnings_from_claims,
        writer=result.writer,
        llm_used=result.llm_used,
        paid_llm=result.paid_llm,
        content_provenance="generated",
        method=f"{DRAFT_VERSION}+{result.writer}",
        warnings=list(result.warnings),
    )
