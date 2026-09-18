"""LLM writer interface for Stage 5.3 — paid default OFF; tests use heuristic."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from aeo_mvp.optimization.models import (
    ContentOptimizationBrief,
    PageIntelligence,
)


@dataclass
class WriterResult:
    title: str | None
    meta_description: str | None
    body_markdown: str
    faq: list[dict[str, str]]
    schema_jsonld: list[dict[str, Any]]
    unsupported_claim_warnings: list[str]
    writer: str
    llm_used: bool
    paid_llm: bool
    warnings: list[str]


class ContentDraftWriter(Protocol):
    """Interface — implementations must not call paid APIs unless explicitly opted in."""

    def write(
        self,
        page: PageIntelligence,
        brief: ContentOptimizationBrief,
        *,
        source_excerpts: list[str] | None = None,
    ) -> WriterResult: ...


class HeuristicDraftWriter:
    """Deterministic draft from brief + observed page signals. Never calls LLM/DO."""

    name = "heuristic_v1"

    def write(
        self,
        page: PageIntelligence,
        brief: ContentOptimizationBrief,
        *,
        source_excerpts: list[str] | None = None,
    ) -> WriterResult:
        warnings: list[str] = []
        unsupported: list[str] = []
        excerpts = source_excerpts or []

        lines: list[str] = []
        title = brief.proposed_title or page.title or page.h1 or "Untitled"
        h1 = brief.proposed_h1 or page.h1 or title
        lines.append(f"# {h1}")
        lines.append("")
        lead = page.meta_description or (
            f"{h1} — grounded summary based on existing page signals."
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
            # Use observed headings as anchors (not invented claims)
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
                continue  # already emitted from page headings
            lines.append(f"{'#' * section.level} {section.heading}")
            lines.append("")
            if section.retain_improve_add == "add":
                lines.append(
                    f"*(Draft placeholder)* Directly answer: {section.heading}. "
                    "Use site-owned facts only; leave [NEEDS_SOURCE] where evidence is missing."
                )
            else:
                lines.append(
                    f"Improve this section for intent={section.intent}. "
                    "Keep claims tied to observed content."
                )
            lines.append("")
            if "[NEEDS_SOURCE]" in lines[-2]:
                unsupported.append(
                    f"Section '{section.heading}' requires sourced evidence before publish"
                )

        faq: list[dict[str, str]] = []
        for item in brief.faq_suggestions:
            q = item.get("question") or ""
            faq.append(
                {
                    "question": q,
                    "answer": (
                        f"{q.rstrip('?')} is addressed on this page in the related section. "
                        "[NEEDS_SOURCE] Expand with verified details only."
                    ),
                }
            )
            unsupported.append(f"FAQ answer for '{q}' contains NEEDS_SOURCE placeholder")

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
                                "acceptedAnswer": {
                                    "@type": "Answer",
                                    "text": f["answer"],
                                },
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

        # Guardrails: never emit fake percentages / invented citations
        body = "\n".join(lines)
        for banned in ("% of users", "studies show", "according to a report we invented"):
            if banned in body.lower():
                unsupported.append(f"Banned pattern detected: {banned}")

        return WriterResult(
            title=title,
            meta_description=brief.proposed_meta_description,
            body_markdown=body.strip() + "\n",
            faq=faq,
            schema_jsonld=schema,
            unsupported_claim_warnings=sorted(set(unsupported)),
            writer=self.name,
            llm_used=False,
            paid_llm=False,
            warnings=warnings,
        )


class PaidLLMDraftWriter:
    """Opt-in paid writer stub — refuses unless paid_llm_opt_in and api_key set.

    Tests must never instantiate this with live keys. Default path uses HeuristicDraftWriter.
    """

    name = "paid_llm_stub_v0"

    def __init__(
        self,
        *,
        paid_llm_opt_in: bool = False,
        api_key: str | None = None,
        model: str | None = None,
    ) -> None:
        self.paid_llm_opt_in = paid_llm_opt_in
        self.api_key = api_key
        self.model = model or "unset"

    def write(
        self,
        page: PageIntelligence,
        brief: ContentOptimizationBrief,
        *,
        source_excerpts: list[str] | None = None,
    ) -> WriterResult:
        if not self.paid_llm_opt_in or not self.api_key:
            # Hard fall back — never call network
            fallback = HeuristicDraftWriter().write(
                page, brief, source_excerpts=source_excerpts
            )
            fallback.warnings = list(fallback.warnings) + [
                "paid_llm_skipped:opt_in_or_key_missing"
            ]
            fallback.writer = f"{self.name}+heuristic_fallback"
            fallback.paid_llm = False
            fallback.llm_used = False
            return fallback
        raise RuntimeError(
            "Paid LLM draft writer is not implemented in MVP; "
            "refusing to call external APIs."
        )


def resolve_writer(
    *,
    paid_llm_opt_in: bool = False,
    api_key: str | None = None,
    model: str | None = None,
) -> ContentDraftWriter:
    """Default: heuristic. Paid path only when explicitly opted in."""
    if paid_llm_opt_in and api_key:
        return PaidLLMDraftWriter(
            paid_llm_opt_in=True, api_key=api_key, model=model
        )
    return HeuristicDraftWriter()
