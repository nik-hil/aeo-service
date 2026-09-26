"""Human-readable VISIBILITY.md pack artifact (OBSERVED + accuracy flags).

Python plumbing only — assembles facts from this run's visibility + accuracy
reports. Distinct from docs/VISIBILITY.md (developer docs).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from aeo_mvp.accuracy import AccuracyReport
    from aeo_mvp.pipeline import AEOReport
    from aeo_mvp.visibility import VisibilityReport


def _pct(rate: float) -> str:
    return f"{rate:.0%}"


def build_visibility_markdown(
    report: AEOReport | None = None,
    *,
    visibility: VisibilityReport | None = None,
    accuracy: AccuracyReport | None = None,
    title: str = "",
    model: str = "",
    llm_used: bool = False,
    retrieval_used: bool = False,
) -> str:
    """Build pack VISIBILITY.md for competitor share + accuracy."""
    if report is not None:
        visibility = report.visibility
        accuracy = getattr(report, "accuracy", None)
        title = report.article.title or title
        model = report.model or model
        llm_used = report.llm_used
        retrieval_used = report.retrieval_used

    assert visibility is not None
    v = visibility
    lines: list[str] = [
        "# VISIBILITY (measurement pack)",
        "",
        "OBSERVED DigitalOcean Responses + `web_search` only.",
        "This is **not** consumer ChatGPT / Gemini / Perplexity UI ranking.",
        "",
        f"**Article:** {title or '(untitled)'}",
        f"**Model:** `{model}`",
        f"**llm_used:** {llm_used} · **retrieval_used:** {retrieval_used}",
        f"**Provider:** {v.provider}",
        f"**Notes:** {v.notes}",
        "",
        "## Target brand rates (OBSERVED)",
        "",
        f"- mention_rate: {_pct(v.mention_rate)}",
        f"- citation_rate: {_pct(v.citation_rate)}",
        f"- target_in_sources_rate (domain): {_pct(v.target_in_sources_rate)}",
        f"- target_page_in_sources_rate: {_pct(v.target_page_in_sources_rate)}",
        f"- target_page_citation_rate: {_pct(v.target_page_citation_rate)}",
        f"- query_coverage: {_pct(v.query_coverage)}",
        f"- observations: {len(v.observations)}",
        "",
    ]

    if v.competitors_configured:
        lines.extend(["## Competitor share (OBSERVED)", ""])
        for s in v.competitor_share:
            domain = s.domain or "—"
            lines.append(
                f"- **{s.name}** (`{domain}`): "
                f"mention={_pct(s.mention_rate)}, "
                f"citation={_pct(s.citation_rate)}, "
                f"domain_in_sources={_pct(s.domain_in_sources_rate)}"
            )
        lines.append("")
    else:
        lines.extend(
            [
                "## Competitor share (OBSERVED)",
                "",
                "_No competitors configured for this run._",
                "",
            ]
        )

    lines.extend(["## Per-prompt observations (OBSERVED)", ""])
    if not v.observations:
        lines.append("_No OBSERVED rows (dry run / paid web_search not used)._")
        lines.append("")
    else:
        for o in v.observations:
            lines.append(f"### {o.query}")
            lines.append(f"- provenance: `{o.provenance}`")
            if o.error:
                lines.append(f"- error: {o.error}")
            else:
                lines.append(f"- mentioned (target): {o.mentioned}")
                lines.append(f"- cited (target): {o.cited}")
                lines.append(
                    f"- target_domain_in_sources: {o.target_domain_in_sources}"
                )
                urls = ", ".join(o.source_urls[:8]) or "—"
                lines.append(f"- source_urls: {urls}")
                if o.competitors:
                    lines.append("- competitors:")
                    for c in o.competitors:
                        lines.append(
                            f"  - {c.name}: mentioned={c.mentioned}, "
                            f"cited={c.cited}, domain_in_sources={c.domain_in_sources}"
                        )
                preview = (o.answer or "")[:500].replace("\n", " ")
                lines.append(f"- answer preview: {preview}")
            lines.append("")

    lines.extend(
        [
            "## Brand-fact / accuracy flags",
            "",
            "Conflict flags are **LLM-GENERATED** over **OBSERVED** answers vs CURRENT.md.",
            "Not a world fact-check beyond those two sources.",
            "",
        ]
    )
    if accuracy is None:
        lines.append("_Accuracy pass not run._")
        lines.append("")
    else:
        lines.append(f"**Notes:** {accuracy.notes}")
        lines.append(f"**Conflicts:** {len(accuracy.conflicts)}")
        lines.append("")
        if accuracy.conflicts:
            for c in accuracy.conflicts:
                lines.append(f"### Conflict — {c.query}")
                lines.append(f"- severity: {c.severity}")
                lines.append(
                    f"- claim (OBSERVED answer): {c.claim_from_observed_answer}"
                )
                lines.append(
                    f"- evidence (CURRENT.md): {c.evidence_quote_from_current}"
                )
                if c.note:
                    lines.append(f"- note (LLM-GENERATED): {c.note}")
                lines.append(f"- provenance: `{c.provenance}`")
                lines.append("")
        else:
            checked = [c for c in accuracy.checks if not c.skipped]
            if checked:
                lines.append("_No conflicts flagged for branded/factual prompts._")
            else:
                lines.append(
                    "_No branded/factual prompts checked "
                    "(or no OBSERVED answers available)._"
                )
            lines.append("")
        skipped = [c for c in accuracy.checks if c.skipped]
        if skipped:
            lines.append("Skipped checks:")
            for c in skipped[:12]:
                lines.append(f"- {c.query} — {c.skip_reason or 'skipped'}")
            if len(skipped) > 12:
                lines.append(f"- …and {len(skipped) - 12} more")
            lines.append("")

    lines.extend(
        [
            "---",
            "",
            "Pack companion to CURRENT.md / RECOMMENDED.md / DIFF / SUMMARY / report.json.",
            "",
        ]
    )
    return "\n".join(lines)
