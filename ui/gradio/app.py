"""Thin Gradio UI — scannable SUMMARY → VISIBILITY → OPPORTUNITIES → DIFF → DETAILS."""

from __future__ import annotations

import html
from pathlib import Path

import gradio as gr

from aeo_mvp.llm import LLMError
from aeo_mvp.pipeline import run_pipeline

_EXAMPLE = Path(__file__).resolve().parents[2] / "examples" / "sample_article.md"

_CSS = """
.aeo-wrap {
  max-width: 1200px !important;
  margin: 0 auto;
  font-family: Inter, -apple-system, BlinkMacSystemFont, "Segoe UI", Arial, sans-serif;
  font-size: 14px;
  font-weight: 400;
  line-height: 1.5;
  color: #1a1a1a;
}
.aeo-wrap h1 {
  font-size: 28px !important;
  font-weight: 700 !important;
  line-height: 1.25;
  margin: 0 0 8px 0 !important;
  color: #111;
}
.aeo-wrap .aeo-subtitle {
  font-size: 14px;
  color: #444;
  margin: 0 0 4px 0;
}
.aeo-wrap .aeo-legend {
  font-size: 12px;
  color: #666;
  margin: 0 0 24px 0;
}
.aeo-wrap h2.aeo-section {
  font-size: 18px !important;
  font-weight: 600 !important;
  margin: 28px 0 12px 0 !important;
  color: #111;
  border-bottom: 1px solid #e5e5e5;
  padding-bottom: 8px;
}
.aeo-metrics {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  margin: 0 0 8px 0;
}
.aeo-metric {
  flex: 1 1 140px;
  min-width: 120px;
  border: 1px solid #e0e0e0;
  border-radius: 8px;
  padding: 16px;
  background: #fff;
}
.aeo-metric .aeo-metric-label {
  font-size: 12px;
  font-weight: 500;
  color: #666;
  text-transform: uppercase;
  letter-spacing: 0.02em;
  margin-bottom: 8px;
}
.aeo-metric .aeo-metric-value {
  font-size: 26px;
  font-weight: 700;
  color: #111;
  line-height: 1.2;
}
.aeo-cards {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  margin: 0 0 12px 0;
}
.aeo-card {
  flex: 1 1 160px;
  min-width: 140px;
  border: 1px solid #e0e0e0;
  border-radius: 8px;
  padding: 16px;
  background: #fff;
}
.aeo-card .aeo-card-label {
  font-size: 12px;
  font-weight: 500;
  color: #666;
  margin-bottom: 8px;
}
.aeo-card .aeo-card-value {
  font-size: 24px;
  font-weight: 700;
  color: #111;
}
.aeo-help {
  cursor: help;
  color: #888;
  font-size: 11px;
  font-weight: 400;
  margin-left: 4px;
  text-transform: none;
  letter-spacing: 0;
}
.aeo-muted {
  font-size: 13px;
  color: #555;
  margin: 0 0 8px 0;
}
.aeo-badge-row {
  font-size: 12px;
  font-weight: 500;
  margin-top: 8px;
}
.aeo-badge-ok { color: #2a6b2a; }
.aeo-badge-fail { color: #b00020; }
.aeo-badge-neutral { color: #666; }
.aeo-opp {
  border: 1px solid #e0e0e0;
  border-radius: 8px;
  padding: 16px;
  margin: 0 0 12px 0;
  background: #fff;
}
.aeo-opp h3 {
  font-size: 15px;
  font-weight: 600;
  margin: 0 0 8px 0;
  color: #111;
}
.aeo-opp .aeo-gap-type {
  font-size: 12px;
  font-weight: 500;
  color: #555;
  text-transform: uppercase;
  letter-spacing: 0.03em;
  margin: 0 0 12px 0;
}
.aeo-opp .aeo-field {
  margin: 0 0 10px 0;
}
.aeo-opp .aeo-field-label {
  font-size: 12px;
  font-weight: 500;
  color: #666;
  margin-bottom: 2px;
}
.aeo-opp .aeo-field-body {
  font-size: 14px;
  color: #222;
}
.aeo-pass { color: #1a7a1a; font-weight: 600; }
.aeo-fail { color: #b00020; font-weight: 600; }
.aeo-warn { color: #8a6d00; font-weight: 600; }
.aeo-error-box {
  border: 1px solid #e0a0a0;
  border-radius: 8px;
  padding: 16px;
  background: #fff8f8;
  color: #8b0000;
  margin: 12px 0 16px 0;
}
.aeo-error-box strong { display: block; margin-bottom: 4px; }
.aeo-info {
  border: 1px solid #e0e0e0;
  border-radius: 8px;
  padding: 16px;
  background: #fafafa;
  color: #555;
  font-size: 14px;
}
"""


def load_example() -> str:
    if _EXAMPLE.is_file():
        return _EXAMPLE.read_text(encoding="utf-8")
    return "# Example\n\nPaste Hashnode Markdown here.\n"


def _esc(value: object) -> str:
    return html.escape(str(value if value is not None else ""), quote=True)


def _fmt_pct(rate: float | None) -> str:
    if rate is None:
        return "—"
    return f"{rate:.0%}"


def _fmt_bool(value: bool | None) -> str:
    if value is None:
        return "—"
    return "yes" if value else "no"


def _gap_type_label(answerability: str | None) -> str:
    key = (answerability or "").strip().lower()
    if key == "missing":
        return "INFORMATION GAP / missing"
    if key == "weak":
        return "CLARITY GAP / weak"
    if key == "strong":
        return "CLARITY GAP / strong"
    return (answerability or "GAP").upper()


# Glossary for visibility KPIs — wording matches pipeline rate definitions.
_KPI_GLOSSARY: dict[str, str] = {
    "Mention": (
        "Answer-engine mentioned the target site/brand in the answer text "
        "(mention_rate)."
    ),
    "Domain": (
        "Target domain appeared in sources "
        "(target_in_sources_rate; domain-level)."
    ),
    "Exact Page": (
        "Exact target page URL appeared in sources "
        "(target_page_in_sources_rate)."
    ),
    "Exact Citation": (
        "Exact target page was cited "
        "(target_page_citation_rate)."
    ),
}


def _label_with_glossary(label: str, *, css_class: str) -> str:
    tip = _KPI_GLOSSARY.get(label)
    if not tip:
        return f'<div class="{css_class}">{_esc(label)}</div>'
    return (
        f'<div class="{css_class}">{_esc(label)}'
        f'<span class="aeo-help" title="{_esc(tip)}">ⓘ</span></div>'
    )


def _validation_badge(report) -> tuple[str, str]:
    """Return (label, css_class) from quality_eval only — no invented flags.

    - passed → Validated
    - failed → Unvalidated
    - skipped (None) → Quality skipped (neutral)
    """
    qe = report.quality_eval
    if qe is None:
        return "Quality skipped", "aeo-badge-neutral"
    if qe.passed:
        return "✓ Validated", "aeo-badge-ok"
    return "Unvalidated", "aeo-badge-fail"


def _quality_label(report) -> str:
    qe = report.quality_eval
    if qe is None:
        return "Quality evaluation — skipped"
    return f"Quality evaluation — {'PASS' if qe.passed else 'FAIL'}"


def _count_substantive_changes(report) -> int:
    edits = getattr(report.recommendations, "section_edits", None) or []
    if edits:
        return len(edits)
    opps = report.recommendations.opportunities or []
    if opps:
        return len(opps)
    diff = report.diff or ""
    n = 0
    for line in diff.splitlines():
        if line.startswith("+++") or line.startswith("---") or line.startswith("@@"):
            continue
        if line.startswith("+") or line.startswith("-"):
            n += 1
    return n


def _summary_html(report) -> str:
    qe = report.quality_eval
    if qe is None:
        quality = "skipped"
        quality_cls = "aeo-warn"
    elif qe.passed:
        quality = "PASS"
        quality_cls = "aeo-pass"
    else:
        quality = "FAIL"
        quality_cls = "aeo-fail"
    v = report.visibility
    metrics = [
        ("Questions", str(len(report.queries.selected))),
        ("Opportunities", str(len(report.recommendations.opportunities))),
        ("Quality", quality, quality_cls),
        ("Exact Page", _fmt_pct(v.target_page_in_sources_rate)),
        ("Exact Citation", _fmt_pct(v.target_page_citation_rate)),
    ]
    parts = ['<div class="aeo-metrics">']
    for item in metrics:
        label, value = item[0], item[1]
        extra = f" {item[2]}" if len(item) > 2 else ""
        parts.append(
            '<div class="aeo-metric">'
            f'{_label_with_glossary(label, css_class="aeo-metric-label")}'
            f'<div class="aeo-metric-value{extra}">{_esc(value)}</div>'
            "</div>"
        )
    parts.append("</div>")
    return "".join(parts)


def _visibility_html(report) -> str:
    v = report.visibility
    cards = [
        ("Mention", _fmt_pct(v.mention_rate)),
        ("Domain", _fmt_pct(v.target_in_sources_rate)),
        ("Exact Page", _fmt_pct(v.target_page_in_sources_rate)),
        ("Exact Citation", _fmt_pct(v.target_page_citation_rate)),
    ]
    parts = ['<div class="aeo-cards">']
    for label, value in cards:
        parts.append(
            '<div class="aeo-card">'
            f'{_label_with_glossary(label, css_class="aeo-card-label")}'
            f'<div class="aeo-card-value">{_esc(value)}</div>'
            "</div>"
        )
    parts.append("</div>")
    ok = sum(1 for o in v.observations if not o.error)
    total = len(v.observations)
    if total == 0:
        parts.append(
            '<p class="aeo-muted">No visibility observations.</p>'
        )
    else:
        parts.append(
            f'<p class="aeo-muted">{ok} / {total} queries successfully observed</p>'
        )
    # Intentional: four-card set prefers PR #50 exact-page KPIs over
    # domain-level citation_rate (still available via query details' cited).
    parts.append(
        '<p class="aeo-muted">Domain-level citation_rate is omitted from these '
        "cards; see each observation&rsquo;s <code>cited</code> flag in Query "
        "details.</p>"
    )
    return "".join(parts)


def _query_details_md(report) -> str:
    v = report.visibility
    if not v.observations:
        return "_No visibility observations._"
    lines: list[str] = []
    for o in v.observations:
        lines.append(f"### {o.query}")
        if o.error:
            lines.append(f"- error: {o.error}")
        else:
            lines.append(f"- mentioned: {o.mentioned}")
            lines.append(f"- cited: {o.cited}")
            lines.append(f"- target_domain_in_sources: {o.target_domain_in_sources}")
            lines.append(
                f"- target_page_in_sources: {_fmt_bool(o.target_page_in_sources)}"
            )
            lines.append(f"- target_page_cited: {_fmt_bool(o.target_page_cited)}")
            urls = ", ".join(o.source_urls[:5]) or "—"
            lines.append(f"- source_urls: {urls}")
            preview = (o.answer or "")[:400].replace("\n", " ")
            if preview:
                lines.append(f"- answer preview: {preview}…")
        lines.append("")
    return "\n".join(lines)


def _opportunities_html(report) -> str:
    opps = report.recommendations.opportunities
    if not opps:
        return '<div class="aeo-info">No material opportunities found.</div>'
    val_label, val_cls = _validation_badge(report)
    parts: list[str] = []
    for o in opps:
        grounded = bool((o.evidence_quote or "").strip())
        badge_bits: list[str] = []
        if grounded:
            badge_bits.append(
                '<span class="aeo-badge-ok">✓ Grounded</span>'
            )
        badge_bits.append(
            f'<span class="{val_cls}">{_esc(val_label)}</span>'
        )
        parts.append(
            '<div class="aeo-opp">'
            f"<h3>{_esc(o.question)}</h3>"
            f'<div class="aeo-gap-type">{_esc(_gap_type_label(o.answerability))}</div>'
            '<div class="aeo-field">'
            '<div class="aeo-field-label">Gap</div>'
            f'<div class="aeo-field-body">{_esc(o.gap)}</div>'
            "</div>"
            '<div class="aeo-field">'
            '<div class="aeo-field-label">Target section</div>'
            f'<div class="aeo-field-body">{_esc(o.target_heading or "—")}</div>'
            "</div>"
            '<div class="aeo-field">'
            '<div class="aeo-field-label">Recommended change</div>'
            f'<div class="aeo-field-body">{_esc(o.recommended_change)}</div>'
            "</div>"
            '<div class="aeo-field">'
            '<div class="aeo-field-label">Evidence</div>'
            f'<div class="aeo-field-body">{_esc(o.evidence_quote or "—")}</div>'
            "</div>"
            f'<div class="aeo-badge-row">{" · ".join(badge_bits)}</div>'
            "</div>"
        )
    warnings = report.recommendations.validation_warnings or []
    if warnings:
        parts.append('<div class="aeo-muted"><strong>Validation warnings</strong><ul>')
        for w in warnings:
            parts.append(f"<li>{_esc(w)}</li>")
        parts.append("</ul></div>")
    return "".join(parts)


def _questions_md(report) -> str:
    selected = report.queries.selected
    if not selected:
        return "_No questions selected._"
    lines = [
        f"**Count:** {len(selected)} (from {len(report.queries.candidates)} candidates)",
        "",
    ]
    for q in selected:
        lines.append(f"### {q.text}")
        lines.append(f"- **Importance:** {q.importance}")
        lines.append(f"- **Reason:** {q.reason or '—'}")
        lines.append(
            f"- **Article evidence:** {q.article_topics_or_evidence or '—'}"
        )
        lines.append("")
    return "\n".join(lines)


def _quality_md(report) -> str:
    qe = report.quality_eval
    if qe is None:
        return "_Quality evaluation skipped._"

    def bullets(items: list[str]) -> list[str]:
        return [f"- {x}" for x in items] if items else ["- —"]

    verdict = "✓ PASS" if qe.passed else "FAIL"
    lines = [
        f"**Verdict:** {verdict}",
        f"**Summary:** {qe.summary}",
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


def _run_details_md(report) -> str:
    v = report.visibility
    a = report.article
    heads = ", ".join(a.section_headings) or "—"
    lines = [
        f"- **Title:** {a.title}",
        f"- **Model:** `{report.model}`",
        f"- **Visibility model:** `{v.model or report.model}`",
        f"- **Provider:** {v.provider}",
        f"- **llm_used:** {report.llm_used}",
        f"- **retrieval_used:** {report.retrieval_used}",
        f"- **auto_publish:** {report.auto_publish}",
        f"- **target_domain:** {a.target_domain or '—'}",
        f"- **target_url:** {a.target_url or '—'}",
        f"- **Provenance:** OBSERVED = search evidence · LLM-GENERATED = questions/recommendations",
        f"- **Visibility notes:** {v.notes}",
        f"- **Sections:** {heads}",
        f"- **Query quality notes:** {report.queries.quality_notes or '—'}",
        f"- **Recommendation source:** `{report.recommendations.source}`",
    ]
    if report.recommendations.change_explanations:
        lines.append("- **Change explanations:**")
        for e in report.recommendations.change_explanations:
            lines.append(f"  - {e}")
    return "\n".join(lines)


def _diff_meta_md(report) -> str:
    n = _count_substantive_changes(report)
    label = "change" if n == 1 else "changes"
    return f"**{n} substantive {label}**"


def _error_html(message: str) -> str:
    return (
        '<div class="aeo-error-box">'
        "<strong>Analysis failed</strong>"
        f"{_esc(message)}"
        "</div>"
    )


def _empty_outputs(error_message: str | None = None):
    err = _error_html(error_message) if error_message else ""
    return (
        err,
        "",
        "",
        "",
        gr.update(label="Query details (0)"),
        "",
        "",
        "",
        gr.update(label="Questions (0)"),
        "",
        gr.update(label="Quality evaluation"),
        "",
        "",
        "",
        "",
    )


def analyze(markdown: str, target_article_url: str, dry_run: bool, skip_eval: bool):
    """Run pipeline and map results into the scannable UI sections.

    Still passes the optional URL through ``target_domain`` so pipeline wiring
    is unchanged (hostname extracted when a full URL is provided).
    """
    md = (markdown or "").strip()
    if not md:
        return _empty_outputs("Provide Hashnode Markdown.")
    try:
        result = run_pipeline(
            text=md,
            target_domain=target_article_url.strip() or None,
            dry_run=dry_run,
            skip_quality_eval=skip_eval,
        )
    except LLMError as exc:
        return _empty_outputs(str(exc))
    except Exception as exc:  # noqa: BLE001 — surface unexpected UI failures once
        return _empty_outputs(str(exc))

    n_obs = len(result.visibility.observations)
    n_q = len(result.queries.selected)
    return (
        "",  # clear error
        _summary_html(result),
        _visibility_html(result),
        _query_details_md(result),
        gr.update(label=f"Query details ({n_obs})"),
        _opportunities_html(result),
        _diff_meta_md(result),
        result.diff or "(no diff)",
        gr.update(label=f"Questions ({n_q})"),
        _questions_md(result),
        gr.update(label=_quality_label(result)),
        _quality_md(result),
        _run_details_md(result),
        result.current_markdown,
        result.recommended_markdown,
    )


def build_app() -> gr.Blocks:
    with gr.Blocks(title="Hashnode AEO PoC", css=_CSS) as demo:
        with gr.Column(elem_classes=["aeo-wrap"]):
            gr.HTML(
                "<h1>Hashnode AEO PoC</h1>"
                '<p class="aeo-subtitle">Analyze a Hashnode article for answer-engine '
                "visibility and content gaps.</p>"
                '<p class="aeo-legend">OBSERVED = search evidence · '
                "LLM-GENERATED = questions/recommendations. "
                "<strong>Never auto-publishes.</strong></p>"
            )

            md_in = gr.Textbox(
                label="Hashnode Markdown",
                lines=18,
                value=load_example(),
                elem_classes=["aeo-md-input"],
            )
            url_in = gr.Textbox(
                label="Target article URL (optional)",
                placeholder="https://example.hashnode.dev/article-name",
                lines=1,
            )
            with gr.Row():
                dry = gr.Checkbox(
                    label="Dry run (skip paid DO web_search; LLM still required)",
                    value=True,
                )
                skip_eval = gr.Checkbox(label="Skip quality evaluation", value=False)
            run_btn = gr.Button("Analyze", variant="primary")

            error_out = gr.HTML()

            gr.HTML('<h2 class="aeo-section">SUMMARY</h2>')
            summary_out = gr.HTML()

            gr.HTML('<h2 class="aeo-section">AI VISIBILITY · OBSERVED</h2>')
            visibility_out = gr.HTML()
            with gr.Accordion("Query details (0)", open=False) as query_acc:
                query_details_out = gr.Markdown()

            gr.HTML('<h2 class="aeo-section">OPPORTUNITIES · LLM-GENERATED</h2>')
            opportunities_out = gr.HTML()

            gr.HTML('<h2 class="aeo-section">DIFF</h2>')
            diff_meta_out = gr.Markdown()
            diff_out = gr.Code(label="DIFF", language="markdown", lines=18)

            gr.HTML('<h2 class="aeo-section">DETAILS</h2>')
            with gr.Accordion("Questions (0)", open=False) as questions_acc:
                questions_out = gr.Markdown()
            with gr.Accordion("Quality evaluation", open=False) as quality_acc:
                quality_out = gr.Markdown()
            with gr.Accordion("Run details", open=False):
                run_details_out = gr.Markdown()
            with gr.Accordion("Full CURRENT", open=False):
                current_out = gr.Code(label="CURRENT.md", language="markdown", lines=14)
            with gr.Accordion("Full RECOMMENDED", open=False):
                recommended_out = gr.Code(
                    label="RECOMMENDED.md", language="markdown", lines=14
                )

        run_btn.click(
            fn=analyze,
            inputs=[md_in, url_in, dry, skip_eval],
            outputs=[
                error_out,
                summary_out,
                visibility_out,
                query_details_out,
                query_acc,
                opportunities_out,
                diff_meta_out,
                diff_out,
                questions_acc,
                questions_out,
                quality_acc,
                quality_out,
                run_details_out,
                current_out,
                recommended_out,
            ],
        )
    return demo


def main() -> None:
    build_app().launch(server_name="127.0.0.1", server_port=7860)


if __name__ == "__main__":
    main()
