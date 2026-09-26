"""Human-skimmable SUMMARY.md for the before→after publish pack.

Python plumbing only: assemble literal facts from the same-run CURRENT /
RECOMMENDED / DIFF / report (visibility, opportunities, quality). No LLM call.
No invented wins, fake citations, or claims that contradict the artifacts.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from aeo_mvp.pipeline import AEOReport

PublishVerdict = Literal["ready_to_publish", "review_first"]


def _pct(rate: float) -> str:
    return f"{rate:.0%}"


def _diff_line_stats(diff: str) -> tuple[int, int]:
    """Count added/removed content lines in a unified diff (ignore headers)."""
    added = 0
    removed = 0
    for line in (diff or "").splitlines():
        if not line or line.startswith(("+++", "---", "@@", "diff ")):
            continue
        if line.startswith("+"):
            added += 1
        elif line.startswith("-"):
            removed += 1
    return added, removed


def publish_verdict(report: AEOReport) -> tuple[PublishVerdict, list[str]]:
    """Decide ready-to-publish vs review-first from artifact facts only."""
    reasons: list[str] = []
    rec = report.recommendations
    qe = report.quality_eval
    added, removed = _diff_line_stats(report.diff)
    has_patch = bool(report.diff.strip()) and (added > 0 or removed > 0)

    if not has_patch:
        reasons.append("DIFF is empty — nothing to publish.")
    if rec.validation_warnings:
        reasons.append(
            f"{len(rec.validation_warnings)} validation warning(s) on recommendations."
        )
    if qe is None:
        reasons.append("Quality evaluation was skipped — review manually.")
    else:
        if not qe.passed:
            reasons.append("quality_eval.passed is false.")
        if qe.unsupported_claims:
            reasons.append(
                f"{len(qe.unsupported_claims)} unsupported claim(s) flagged."
            )
        if qe.unnecessary_changes:
            reasons.append(
                f"{len(qe.unnecessary_changes)} unnecessary change(s) flagged."
            )

    if reasons:
        return "review_first", reasons

    reasons.append("quality_eval.passed is true.")
    reasons.append("No validation warnings.")
    reasons.append(f"DIFF has +{added}/-{removed} line changes.")
    reasons.append("auto_publish is always false — human must publish.")
    return "ready_to_publish", reasons


def build_summary_markdown(report: AEOReport) -> str:
    """Build SUMMARY.md text grounded in this run's report artifacts."""
    verdict, verdict_reasons = publish_verdict(report)
    verdict_label = (
        "Ready to publish (human review still required; never auto-publishes)"
        if verdict == "ready_to_publish"
        else "Review first — do not publish until issues below are cleared"
    )

    v = report.visibility
    rec = report.recommendations
    qe = report.quality_eval
    added, removed = _diff_line_stats(report.diff)
    headings = [e.target_heading for e in rec.section_edits if e.target_heading]

    lines: list[str] = [
        "# Publish pack SUMMARY",
        "",
        "Skimmable before→after review for this run. Facts below come from the same",
        "artifacts as CURRENT.md / RECOMMENDED.md / DIFF.patch / report.json.",
        "Nothing here invents wins or citations.",
        "",
        f"**Article:** {report.article.title or '(untitled)'}",
        f"**Model:** `{report.model}`",
        f"**llm_used:** {report.llm_used} · **retrieval_used:** {report.retrieval_used}",
        f"**auto_publish:** {report.auto_publish} (pipeline never publishes)",
        f"**Publish guidance:** {verdict_label}",
        "",
        "## What was weak for AI visibility",
        "",
    ]

    if report.retrieval_used and v.observations:
        lines.extend(
            [
                "**OBSERVED** (DigitalOcean Responses + `web_search` — not consumer "
                "ChatGPT / Gemini / Perplexity UI ranking):",
                f"- mention_rate: {_pct(v.mention_rate)}",
                f"- citation_rate: {_pct(v.citation_rate)}",
                f"- target_in_sources_rate (domain): {_pct(v.target_in_sources_rate)}",
                f"- target_page_in_sources_rate: {_pct(v.target_page_in_sources_rate)}",
                f"- target_page_citation_rate: {_pct(v.target_page_citation_rate)}",
                f"- query_coverage: {_pct(v.query_coverage)}",
                f"- observations: {len(v.observations)}",
                "",
            ]
        )
        weak_obs = [
            o
            for o in v.observations
            if o.error is None and (not o.mentioned or not o.cited)
        ]
        if weak_obs:
            lines.append("Queries with weak mention/citation (OBSERVED):")
            for o in weak_obs[:8]:
                lines.append(
                    f"- {o.query} — mentioned={o.mentioned}, cited={o.cited}"
                )
            if len(weak_obs) > 8:
                lines.append(f"- …and {len(weak_obs) - 8} more")
            lines.append("")
    elif not report.retrieval_used:
        lines.extend(
            [
                "_No OBSERVED visibility rows this run "
                "(dry run / paid `web_search` not used)._",
                "",
            ]
        )
    else:
        lines.extend(
            [
                "_Visibility ran but produced no observations._",
                "",
            ]
        )

    if rec.opportunities:
        lines.append("**LLM-GENERATED** gaps (from opportunities in this run):")
        for o in rec.opportunities:
            gap = (o.gap or "").strip() or "(no gap text)"
            heading = o.target_heading or "(no target heading)"
            lines.append(f"- [{o.answerability}] {heading}: {gap}")
        lines.append("")
    else:
        lines.extend(
            [
                "_No LLM-GENERATED opportunities recorded for this run._",
                "",
            ]
        )

    lines.extend(["## What RECOMMENDED fixes", ""])
    if rec.change_explanations:
        for e in rec.change_explanations:
            lines.append(f"- {e}")
    elif rec.opportunities:
        for o in rec.opportunities:
            change = (o.recommended_change or "").strip() or "(no change text)"
            heading = o.target_heading or "(no target heading)"
            lines.append(f"- {heading}: {change}")
    else:
        lines.append("_No recommended fixes recorded._")
    lines.append("")

    lines.extend(
        [
            "## Patch at a glance",
            "",
            f"- Section edits applied: {len(rec.section_edits)}",
        ]
    )
    if headings:
        lines.append(f"- Headings touched: {', '.join(headings)}")
    else:
        lines.append("- Headings touched: (none)")
    lines.append(f"- DIFF line changes: +{added} / -{removed}")
    if not report.diff.strip():
        lines.append("- DIFF: empty")
    lines.append("")

    lines.extend(
        [
            "## Ready to publish vs review first",
            "",
            f"**Verdict:** `{verdict}`",
            "",
        ]
    )
    for r in verdict_reasons:
        lines.append(f"- {r}")
    lines.append("")

    if qe is not None:
        lines.extend(
            [
                "**Quality evaluation (LLM-GENERATED):**",
                f"- passed: {qe.passed}",
                f"- summary: {qe.summary or '—'}",
                "",
            ]
        )
    if rec.validation_warnings:
        lines.append("**Validation warnings (Python plumbing):**")
        for w in rec.validation_warnings:
            lines.append(f"- {w}")
        lines.append("")

    lines.extend(
        [
            "## Artifacts in this pack",
            "",
            "- `CURRENT.md`",
            "- `RECOMMENDED.md`",
            "- `DIFF.patch`",
            "- `report.json`",
            "- `SUMMARY.md` (this file)",
            "",
            "Open CURRENT / RECOMMENDED / DIFF to verify every claim before publishing.",
            "",
        ]
    )
    return "\n".join(lines)
