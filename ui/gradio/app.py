"""Thin Gradio UI for the Hashnode Markdown AEO PoC.

One screen: ARTICLE | AI VISIBILITY | OPPORTUNITIES | CURRENT vs RECOMMENDED | DIFF.
Does not auto-publish.
"""

from __future__ import annotations

from pathlib import Path

import gradio as gr

from aeo_mvp.pipeline import run_pipeline

_EXAMPLE = Path(__file__).resolve().parents[2] / "examples" / "sample_article.md"


def _fmt_visibility(report) -> str:
    lines = [
        f"**Provider:** {report.visibility.provider}",
        f"**Notes:** {report.visibility.notes}",
        f"**Mention rate:** {report.visibility.mention_rate:.0%}",
        f"**Citation rate:** {report.visibility.citation_rate:.0%}",
        f"**Target-in-sources rate:** {report.visibility.target_in_sources_rate:.0%}",
        f"**llm_used:** {report.llm_used} (actual execution)",
        f"**retrieval_used:** {report.retrieval_used} (tool evidence only)",
        f"**auto_publish:** {report.auto_publish}",
        "",
    ]
    if not report.visibility.observations:
        lines.append("_No live observations (dry run or missing AEO_LLM_API_KEY)._")
        return "\n".join(lines)
    for o in report.visibility.observations:
        lines.append(f"### {o.query}")
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


def _fmt_opportunities(report) -> str:
    if not report.recommendations:
        return "_No opportunities._"
    blocks: list[str] = []
    for r in report.recommendations:
        blocks.append(
            "\n".join(
                [
                    f"### {r.question}",
                    f"- **answerability:** {r.answerability}",
                    f"- **target_heading:** {r.target_heading}",
                    f"- **source:** {r.source} (observed=from visibility; generated=analysis only)",
                    f"- **evidence_quote:** {r.evidence_quote or '—'}",
                    f"- **problem:** {r.problem}",
                    f"- **proposed_change:**\n\n{r.proposed_change}",
                ]
            )
        )
    return "\n\n---\n\n".join(blocks)


def _fmt_article(report) -> str:
    a = report.article
    headings = "\n".join(f"- {h}" for h in a.section_headings) or "—"
    queries = "\n".join(f"- {q}" for q in report.queries.texts) or "—"
    return (
        f"**Title:** {a.title}\n\n"
        f"**Sections:**\n{headings}\n\n"
        f"**Intro (H1 body only — not mega-corpus):**\n\n{a.intro[:1200]}\n\n"
        f"**Selected queries ({len(report.queries.selected)} of "
        f"{len(report.queries.candidates)} candidates):**\n{queries}"
    )


def analyze(
    markdown: str,
    target_domain: str,
    dry_run: bool,
) -> tuple[str, str, str, str, str, str]:
    md = (markdown or "").strip()
    if not md:
        empty = "Provide Hashnode Markdown."
        return empty, empty, empty, "", "", ""
    result = run_pipeline(
        text=md,
        target_domain=target_domain.strip() or None,
        dry_run=dry_run,
    )
    return (
        _fmt_article(result),
        _fmt_visibility(result),
        _fmt_opportunities(result),
        result.current_markdown,
        result.recommended_markdown,
        result.diff or "(no diff — recommendations did not change Markdown)",
    )


def load_example() -> str:
    if _EXAMPLE.is_file():
        return _EXAMPLE.read_text(encoding="utf-8")
    return "# Example\n\nPaste Hashnode Markdown here.\n"


def build_app() -> gr.Blocks:
    with gr.Blocks(title="Hashnode AEO PoC") as demo:
        gr.Markdown(
            "# Hashnode AEO PoC\n"
            "Markdown → queries → AI-search visibility (DigitalOcean web_search) → "
            "opportunities → grounded recommendations. **Never auto-publishes.**"
        )
        with gr.Row():
            md_in = gr.Textbox(
                label="Hashnode Markdown",
                lines=22,
                value=load_example(),
            )
            with gr.Column():
                domain = gr.Textbox(
                    label="Target domain (optional)",
                    placeholder="example.com",
                )
                dry = gr.Checkbox(
                    label="Dry run (skip live DigitalOcean visibility)",
                    value=True,
                )
                run_btn = gr.Button("Analyze", variant="primary")

        gr.Markdown("## ARTICLE")
        article_out = gr.Markdown()
        gr.Markdown("## AI VISIBILITY")
        vis_out = gr.Markdown()
        gr.Markdown("## OPPORTUNITIES")
        opp_out = gr.Markdown()
        gr.Markdown("## CURRENT vs RECOMMENDED")
        with gr.Row():
            current_out = gr.Code(label="CURRENT.md", language="markdown")
            recommended_out = gr.Code(label="RECOMMENDED.md", language="markdown")
        gr.Markdown("## DIFF")
        diff_out = gr.Code(label="DIFF", language="markdown")

        run_btn.click(
            fn=analyze,
            inputs=[md_in, domain, dry],
            outputs=[
                article_out,
                vis_out,
                opp_out,
                current_out,
                recommended_out,
                diff_out,
            ],
        )
    return demo


def main() -> None:
    app = build_app()
    app.launch(server_name="127.0.0.1", server_port=7860)


if __name__ == "__main__":
    main()
