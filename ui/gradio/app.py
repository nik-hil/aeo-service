"""Thin Gradio UI — OBSERVED vs LLM-GENERATED clearly marked."""

from __future__ import annotations

from pathlib import Path

import gradio as gr

from aeo_mvp.llm import LLMError
from aeo_mvp.pipeline import run_pipeline

_EXAMPLE = Path(__file__).resolve().parents[2] / "examples" / "sample_article.md"


def load_example() -> str:
    if _EXAMPLE.is_file():
        return _EXAMPLE.read_text(encoding="utf-8")
    return "# Example\n\nPaste Hashnode Markdown here.\n"


def _article_md(report) -> str:
    a = report.article
    heads = "\n".join(f"- {h}" for h in a.section_headings) or "—"
    return (
        f"**Title:** {a.title}\n\n"
        f"**Model:** `{report.model}`\n\n"
        f"**Sections:**\n{heads}\n\n"
        f"**Intro preview:**\n\n{(a.intro or '')[:1200]}"
    )


def _visibility_md(report) -> str:
    v = report.visibility
    lines = [
        f"**Label:** OBSERVED (API) — not consumer ChatGPT/Gemini UI",
        f"**Provider:** {v.provider}",
        f"**Model (visibility):** `{v.model or report.model}`",
        f"**Notes:** {v.notes}",
        f"**mention_rate:** {v.mention_rate:.0%}",
        f"**citation_rate:** {v.citation_rate:.0%}",
        f"**target_in_sources_rate:** {v.target_in_sources_rate:.0%}",
        f"**query_coverage:** {v.query_coverage:.0%}",
        f"**llm_used:** {report.llm_used} (execution)",
        f"**retrieval_used:** {report.retrieval_used} (tool evidence only)",
        f"**auto_publish:** {report.auto_publish}",
        "",
    ]
    if not v.observations:
        lines.append("_No OBSERVED visibility rows (dry run / no paid search)._")
        return "\n".join(lines)
    for o in v.observations:
        lines.append(f"### {o.query}")
        lines.append(f"- provenance: `{o.provenance}` (OBSERVED)")
        if o.error:
            lines.append(f"- error: {o.error}")
        else:
            lines.append(f"- mentioned: {o.mentioned}")
            lines.append(f"- cited: {o.cited}")
            lines.append(f"- target_domain_in_sources: {o.target_domain_in_sources}")
            lines.append(f"- source_urls: {', '.join(o.source_urls[:5]) or '—'}")
            preview = (o.answer or "")[:400].replace("\n", " ")
            lines.append(f"- answer: {preview}…")
        lines.append("")
    return "\n".join(lines)


def _questions_md(report) -> str:
    lines = [
        "**Label:** LLM-GENERATED (then LLM quality-validated)",
        f"**Count:** {len(report.queries.selected)} "
        f"(from {len(report.queries.candidates)} candidates)",
        f"**Notes:** {report.queries.quality_notes or '—'}",
        "",
    ]
    for q in report.queries.selected:
        lines.append(f"### {q.text}")
        lines.append(f"- importance: {q.importance}")
        lines.append(f"- reason: {q.reason or '—'}")
        lines.append(f"- article_topics_or_evidence: {q.article_topics_or_evidence or '—'}")
        lines.append(f"- source: `{q.source}`")
        lines.append("")
    return "\n".join(lines)


def _opportunities_md(report) -> str:
    lines = ["**Label:** LLM-GENERATED opportunities (grounded + validated)", ""]
    for o in report.recommendations.opportunities:
        lines.extend(
            [
                f"### {o.question}",
                f"- answerability: {o.answerability}",
                f"- target_heading: {o.target_heading or '—'}",
                f"- evidence_quote: {o.evidence_quote or '—'}",
                f"- problem: {o.problem}",
                f"- recommended_change: {o.recommended_change}",
                f"- source: `{o.source}`",
                "",
            ]
        )
    if report.recommendations.change_explanations:
        lines.append("### Change explanations")
        for e in report.recommendations.change_explanations:
            lines.append(f"- {e}")
    if report.recommendations.validation_warnings:
        lines.append("### Validation warnings")
        for w in report.recommendations.validation_warnings:
            lines.append(f"- {w}")
    return "\n".join(lines) if report.recommendations.opportunities else "_None._"


def _quality_md(report) -> str:
    qe = report.quality_eval
    if qe is None:
        return "_Quality evaluation skipped._"
    def bullets(items: list[str]) -> list[str]:
        return [f"- {x}" for x in items] if items else ["- —"]

    lines = [
        "**Label:** LLM-GENERATED quality evaluation",
        f"**passed:** {qe.passed}",
        f"**summary:** {qe.summary}",
        "",
        "### Question feedback",
        *bullets(qe.question_feedback),
        "",
        "### Recommendation feedback",
        *bullets(qe.recommendation_feedback),
        "",
        "### Unsupported claims",
        *bullets(qe.unsupported_claims),
        "",
        "### Unnecessary changes",
        *bullets(qe.unnecessary_changes),
        "",
        "### Explanations",
        *bullets(qe.explanations),
    ]
    return "\n".join(lines)


def analyze(markdown: str, target_domain: str, dry_run: bool, skip_eval: bool):
    md = (markdown or "").strip()
    if not md:
        empty = "Provide Hashnode Markdown."
        return empty, empty, empty, empty, "", "", "", empty
    try:
        result = run_pipeline(
            text=md,
            target_domain=target_domain.strip() or None,
            dry_run=dry_run,
            skip_quality_eval=skip_eval,
        )
    except LLMError as exc:
        err = f"**Error:** {exc}"
        return err, err, err, err, "", "", "", err
    return (
        _article_md(result),
        _visibility_md(result),
        _questions_md(result),
        _opportunities_md(result),
        result.current_markdown,
        result.recommended_markdown,
        result.diff or "(no diff)",
        _quality_md(result),
    )


def build_app() -> gr.Blocks:
    with gr.Blocks(title="Hashnode AEO PoC") as demo:
        gr.Markdown(
            "# Hashnode AEO PoC\n"
            "LLM owns question/opportunity/recommendation semantics. "
            "Python owns Markdown parsing, validation, DIFF, and DO web_search plumbing. "
            "**Never auto-publishes.** "
            "Labels: **OBSERVED** (API visibility) vs **LLM-GENERATED**."
        )
        with gr.Row():
            md_in = gr.Textbox(label="Hashnode Markdown", lines=20, value=load_example())
            with gr.Column():
                domain = gr.Textbox(label="Target domain (optional)", placeholder="example.com")
                dry = gr.Checkbox(
                    label="Dry run (skip paid DO web_search; LLM still required)",
                    value=True,
                )
                skip_eval = gr.Checkbox(label="Skip quality evaluation", value=False)
                run_btn = gr.Button("Analyze", variant="primary")

        gr.Markdown("## ARTICLE")
        article_out = gr.Markdown()
        gr.Markdown("## AI VISIBILITY *(OBSERVED)*")
        vis_out = gr.Markdown()
        gr.Markdown("## QUESTIONS *(LLM-GENERATED)*")
        q_out = gr.Markdown()
        gr.Markdown("## OPPORTUNITIES *(LLM-GENERATED)*")
        opp_out = gr.Markdown()
        gr.Markdown("## CURRENT vs RECOMMENDED")
        with gr.Row():
            current_out = gr.Code(label="CURRENT.md", language="markdown")
            recommended_out = gr.Code(label="RECOMMENDED.md", language="markdown")
        gr.Markdown("## DIFF")
        diff_out = gr.Code(label="DIFF", language="markdown")
        gr.Markdown("## QUALITY EVALUATION *(LLM-GENERATED)*")
        qual_out = gr.Markdown()

        run_btn.click(
            fn=analyze,
            inputs=[md_in, domain, dry, skip_eval],
            outputs=[
                article_out,
                vis_out,
                q_out,
                opp_out,
                current_out,
                recommended_out,
                diff_out,
                qual_out,
            ],
        )
    return demo


def main() -> None:
    build_app().launch(server_name="127.0.0.1", server_port=7860)


if __name__ == "__main__":
    main()
