"""Thin Gradio UI — OBSERVED vs LLM-GENERATED clearly marked."""

from __future__ import annotations

from pathlib import Path
from urllib.parse import urlparse

import gradio as gr
import httpx

from aeo_mvp.llm import LLMError
from aeo_mvp.pipeline import run_pipeline

_EXAMPLE = Path(__file__).resolve().parents[2] / "examples" / "sample_article.md"

_FETCH_TIMEOUT_S = 30.0

STATUS_URL_IGNORES_PASTE = "Using target URL (Markdown paste ignored)."
STATUS_URL = "Using target URL."
STATUS_MARKDOWN = "Using Hashnode Markdown paste."
STATUS_DOMAIN_AND_MARKDOWN = (
    "Using Hashnode Markdown paste; target domain used for visibility only."
)

_CSS = """
/* Fixed-height CURRENT / RECOMMENDED / DIFF panes with vertical scroll */
.aeo-md-scroll textarea {
  max-height: 28rem !important;
  overflow-y: auto !important;
}
.aeo-md-scroll .cm-editor,
.aeo-md-scroll .cm-scroller {
  max-height: 28rem !important;
  overflow-y: auto !important;
}
.aeo-md-scroll .cm-content {
  overflow-wrap: anywhere;
}
"""


def load_example() -> str:
    if _EXAMPLE.is_file():
        return _EXAMPLE.read_text(encoding="utf-8")
    return "# Example\n\nPaste Hashnode Markdown here.\n"


def _is_absolute_http_url(value: str) -> bool:
    return value.startswith(("http://", "https://"))


def _canonical_article_url(url: str) -> str:
    """Strip a trailing ``.md`` so visibility identity matches the HTML article."""
    cleaned = url.strip()
    parsed = urlparse(cleaned)
    path = parsed.path or ""
    if path.endswith(".md"):
        path = path[: -len(".md")] or "/"
        cleaned = parsed._replace(path=path).geturl()
    return cleaned


def fetch_markdown_from_url(
    url: str,
    *,
    client: httpx.Client | None = None,
) -> str:
    """Fetch Hashnode / supported article Markdown from an absolute http(s) URL.

    Tries, in order:
    1. URL as-is when it already ends with ``.md``
    2. Same URL with ``Accept: text/markdown``
    3. URL with ``.md`` appended to the path
    """
    cleaned = url.strip()
    if not _is_absolute_http_url(cleaned):
        raise ValueError("Target must be an absolute http(s) URL to fetch Markdown.")

    own_client = client is None
    http = client or httpx.Client(timeout=_FETCH_TIMEOUT_S, follow_redirects=True)
    try:
        candidates: list[tuple[str, dict[str, str]]] = []
        if cleaned.lower().endswith(".md"):
            candidates.append((cleaned, {}))
        else:
            candidates.append((cleaned, {"Accept": "text/markdown"}))
            parsed = urlparse(cleaned)
            md_path = (parsed.path or "").rstrip("/") + ".md"
            candidates.append((parsed._replace(path=md_path).geturl(), {}))

        last_error = "Could not fetch Markdown from target URL."
        for candidate, headers in candidates:
            try:
                resp = http.get(candidate, headers=headers)
            except httpx.HTTPError as exc:
                last_error = f"Failed to fetch target URL: {exc}"
                continue
            if resp.status_code >= 400:
                last_error = (
                    f"Failed to fetch target URL "
                    f"({resp.status_code} for {candidate})."
                )
                continue
            text = (resp.text or "").strip()
            if not text:
                last_error = f"Target URL returned empty Markdown ({candidate})."
                continue
            content_type = (resp.headers.get("content-type") or "").lower()
            # Prefer explicit markdown / plain text; reject obvious HTML shells.
            if "html" in content_type and "markdown" not in content_type:
                if text.lstrip().lower().startswith(
                    ("<!doctype", "<html", "<head", "<body")
                ):
                    last_error = (
                        "Target URL returned HTML, not Markdown. "
                        "Use a Hashnode article URL or …/slug.md."
                    )
                    continue
            return text
        raise ValueError(last_error)
    finally:
        if own_client:
            http.close()


def resolve_content_source(
    markdown: str,
    target: str,
    *,
    fetch_fn=None,
) -> tuple[str, str | None, str]:
    """Resolve exclusive content source for Analyze.

    Rules:
    - Absolute http(s) **target URL** → fetch Markdown; **ignore** paste;
      pass URL through as ``target_domain`` (hostname extracted in pipeline).
    - Non-empty **bare domain** (no scheme) → use paste (required) for content;
      domain is visibility identity only.
    - Empty target → use Hashnode Markdown paste.
    - Both empty → ``ValueError``.
    """
    md = (markdown or "").strip()
    tgt = (target or "").strip()
    fetcher = fetch_fn or fetch_markdown_from_url

    if tgt and _is_absolute_http_url(tgt):
        fetched = fetcher(tgt).strip()
        if not fetched:
            raise ValueError("Target URL returned empty Markdown.")
        note = STATUS_URL_IGNORES_PASTE if md else STATUS_URL
        return fetched, _canonical_article_url(tgt), note

    if tgt:
        # Bare domain / non-URL token: visibility identity only (legacy).
        if not md:
            raise ValueError(
                "Provide Hashnode Markdown, or a full article URL "
                "(https://…/slug or …/slug.md)."
            )
        return md, tgt, STATUS_DOMAIN_AND_MARKDOWN

    if md:
        return md, None, STATUS_MARKDOWN

    raise ValueError(
        "Provide Hashnode Markdown or a target article URL "
        "(https://…/slug or …/slug.md)."
    )


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
                f"- gap: {o.gap}",
                f"- target_heading: {o.target_heading or '—'}",
                f"- evidence_quote: {o.evidence_quote or '—'}",
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


def _error_outputs(message: str):
    err = f"**Error:** {message}"
    return err, err, err, err, err, "", "", "", "", err


def analyze(
    markdown: str,
    target: str,
    dry_run: bool,
    skip_eval: bool,
    *,
    fetch_fn=None,
    pipeline_fn=None,
):
    """Run pipeline with URL-vs-paste exclusivity.

    Absolute target URLs are fetched and used as Markdown; paste is ignored for
    that run. Bare domains keep legacy paste + visibility identity behavior.
    """
    try:
        md, target_domain, status = resolve_content_source(
            markdown, target, fetch_fn=fetch_fn
        )
    except ValueError as exc:
        return _error_outputs(str(exc))

    run = pipeline_fn or run_pipeline
    try:
        result = run(
            text=md,
            target_domain=target_domain,
            dry_run=dry_run,
            skip_quality_eval=skip_eval,
        )
    except LLMError as exc:
        return _error_outputs(str(exc))
    return (
        status,
        _article_md(result),
        _visibility_md(result),
        _questions_md(result),
        _opportunities_md(result),
        result.current_markdown,
        result.recommended_markdown,
        result.diff or "(no diff)",
        getattr(result, "summary_markdown", None) or "(no SUMMARY.md)",
        _quality_md(result),
    )


def build_app() -> gr.Blocks:
    with gr.Blocks(title="Hashnode AEO PoC", css=_CSS) as demo:
        gr.Markdown(
            "# Hashnode AEO PoC\n"
            "LLM owns question/opportunity/recommendation semantics. "
            "Python owns Markdown parsing, validation, DIFF, and DO web_search plumbing. "
            "**Never auto-publishes.** "
            "Labels: **OBSERVED** (API visibility) vs **LLM-GENERATED**.\n\n"
            "**Input rule:** a full target article URL is fetched and used as the "
            "content source (Markdown paste ignored). If the URL field is empty, "
            "pasted Hashnode Markdown is used. A bare domain alone is visibility "
            "identity only and still needs Markdown paste."
        )
        with gr.Row():
            md_in = gr.Textbox(label="Hashnode Markdown", lines=20, value=load_example())
            with gr.Column():
                target_in = gr.Textbox(
                    label="Target article URL / domain (optional)",
                    placeholder="https://example.hashnode.dev/my-article or example.com",
                    lines=1,
                )
                dry = gr.Checkbox(
                    label="Dry run (skip paid DO web_search; LLM still required)",
                    value=True,
                )
                skip_eval = gr.Checkbox(label="Skip quality evaluation", value=False)
                run_btn = gr.Button("Analyze", variant="primary")
                status_out = gr.Markdown()

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
            current_out = gr.Code(
                label="CURRENT.md",
                language="markdown",
                lines=20,
                max_lines=20,
                elem_classes=["aeo-md-scroll"],
            )
            recommended_out = gr.Code(
                label="RECOMMENDED.md",
                language="markdown",
                lines=20,
                max_lines=20,
                elem_classes=["aeo-md-scroll"],
            )
        gr.Markdown("## DIFF")
        diff_out = gr.Code(
            label="DIFF",
            language="markdown",
            lines=16,
            max_lines=16,
            elem_classes=["aeo-md-scroll"],
        )
        gr.Markdown("## SUMMARY.md *(publish review)*")
        summary_out = gr.Code(
            label="SUMMARY.md",
            language="markdown",
            lines=16,
            max_lines=16,
            elem_classes=["aeo-md-scroll"],
        )
        gr.Markdown("## QUALITY EVALUATION *(LLM-GENERATED)*")
        qual_out = gr.Markdown()

        run_btn.click(
            fn=analyze,
            inputs=[md_in, target_in, dry, skip_eval],
            outputs=[
                status_out,
                article_out,
                vis_out,
                q_out,
                opp_out,
                current_out,
                recommended_out,
                diff_out,
                summary_out,
                qual_out,
            ],
        )
    return demo


def main() -> None:
    build_app().launch(server_name="127.0.0.1", server_port=7860)


if __name__ == "__main__":
    main()
