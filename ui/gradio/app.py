"""AEO Leadership Demo — Gradio application.

Presentation-only. All analysis goes through the secured AEO API.
Never fetches target URLs from the browser/UI process for crawling.
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path
from typing import Any, Generator

_ROOT = Path(__file__).resolve().parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

# Avoid local folder shadowing the third-party Gradio package when `.../ui` is
# on sys.path (pytest collection artifact for ui/gradio/).
_ui_parent = str(_ROOT.parent)
if _ui_parent in sys.path:
    sys.path = [p for p in sys.path if Path(p).resolve() != Path(_ui_parent).resolve()]
_bad = sys.modules.get("gradio")
if _bad is not None:
    _f = str(getattr(_bad, "__file__", "") or "")
    if "site-packages" not in _f and "/ui/gradio" in _f:
        del sys.modules["gradio"]
        for _k in list(sys.modules):
            if _k.startswith("gradio."):
                del sys.modules[_k]

from glossary import GUIDE_MARKDOWN, all_terms_markdown, info_text
from services.adapters import (
    AnalysisState,
    adapt_before,
    adapt_brief,
    adapt_draft,
    adapt_evidence,
    adapt_overview,
    adapt_pages,
    adapt_recommendations,
    merge_page_opt_into_report,
    overview_markdown,
    pages_table,
    recommendations_markdown,
)
from services.api_client import AeoApiClient, AeoApiError
from services.opportunities import build_opportunities, opportunities_table
from services.sanitize import escape_text
from styles.theme import CUSTOM_CSS, build_theme

STAGE_LABELS = {
    "pending": "Queued",
    "claimed": "Claimed by worker",
    "crawling": "Crawling pages (same-host)",
    "analyzing": "Analyzing content & structure",
    "scoring": "Computing AEO Health (health-v1)",
    "experimenting": "Running visibility experiment",
    "synthesizing": "Synthesizing recommendations",
    "completed": "Complete",
    "failed": "Failed",
}

EMPTY_OVERVIEW = "_Run an analysis to see AEO Health, gaps, and recommendations._"
EMPTY_DETAIL = (
    "_Select a page (multi-page) or run analysis (single-page) to inspect "
    "Before → Recommendations → After → Evidence._"
)
OPP_HEADERS = ["#", "Kind", "Title", "Summary", "Page", "Signal"]
PAGE_HEADERS = ["Title", "URL", "Depth", "Status", "Error"]

AnalysisOutput = tuple[Any, ...]


def _client() -> AeoApiClient:
    return AeoApiClient()


def _validate_url(url: str) -> str | None:
    u = (url or "").strip()
    if not u:
        return "Enter a URL to analyze."
    if not u.startswith(("http://", "https://")):
        return "URL must start with http:// or https://."
    return None


def gr_update_status(message: str, *, kind: str = "idle") -> str:
    css = {
        "ok": "aeo-status-ok",
        "err": "aeo-status-err",
        "busy": "aeo-status-busy",
        "idle": "",
    }.get(kind, "")
    if not message:
        return ""
    return f'<p class="{css}">{escape_text(message)}</p>'


def clear_state(state: AnalysisState | None) -> AnalysisState:
    s = state or AnalysisState()
    s.clear_results()
    return s


def detail_panels(report: dict[str, Any], page_url: str | None) -> tuple[str, str, str, str]:
    before = adapt_before(report, page_url=page_url)
    brief = adapt_brief(report, page_url=page_url)
    draft = adapt_draft(report, page_url=page_url)
    recs = adapt_recommendations(report, page_url=page_url)
    evidence = adapt_evidence(report, page_url=page_url)
    brief_md = brief.markdown if brief else "_No optimization brief for this page._"
    draft_md = (
        draft.body_markdown
        if draft
        else (
            "_No content draft returned. When enabled, drafts are deterministic skeletons "
            "or generated suggestions — never a final optimized page._"
        )
    )
    after_md = brief_md + "\n\n---\n\n" + draft_md
    return before.markdown, recommendations_markdown(recs), after_md, evidence.markdown


def _blank_ui(state: AnalysisState, status: str, *, kind: str = "err") -> AnalysisOutput:
    import gradio as gr

    return (
        state,
        gr_update_status(status, kind=kind),
        EMPTY_OVERVIEW,
        [],
        [],
        EMPTY_DETAIL,
        "_No recommendations yet._",
        "_No after content yet._",
        "_No evidence yet._",
        gr.update(choices=[], value=None),
    )


def run_analysis(
    url: str,
    mode: str,
    use_demo: bool,
    include_draft: bool,
    state: AnalysisState | None,
) -> Generator[AnalysisOutput, None, None]:
    """Clear stale results, create job, poll, adapt report."""
    import gradio as gr

    state = clear_state(state)
    mode_key = "multi" if str(mode).startswith("Multi") else "single"

    if use_demo:
        url = "https://demo.example/"
    else:
        err = _validate_url(url)
        if err:
            state.error = err
            yield _blank_ui(state, err, kind="err")
            return

    options: dict[str, Any] = {
        "provider": "demo" if use_demo else "auto",
        "content_optimization": True,
        "content_draft": bool(include_draft or use_demo),
    }
    if mode_key == "single":
        options["max_pages"] = 1
        options["max_depth"] = 0
    else:
        options["max_pages"] = 10
        options["max_depth"] = 2

    client = _client()
    try:
        yield _blank_ui(state, "Starting analysis…", kind="busy")

        job = client.create_job(url, demo_mode=use_demo, options=options)
        state.job_id = job.id
        state.mode = mode_key
        state.stage = "pending"

        deadline = time.monotonic() + float(os.environ.get("AEO_UI_JOB_TIMEOUT", "180"))
        last_status = ""
        while time.monotonic() < deadline:
            payload = client.get_job(job.id)
            status = str(payload.get("status") or "")
            state.stage = status
            if status != last_status:
                label = STAGE_LABELS.get(status, status)
                yield _blank_ui(state, f"Stage: {label}", kind="busy")
                last_status = status
            if status == "completed":
                break
            if status == "failed":
                msg = str(payload.get("error_message") or "Analysis failed")
                state.clear_results()
                state.error = msg
                yield _blank_ui(state, f"Analysis failed: {msg}", kind="err")
                return
            time.sleep(0.45)
        else:
            state.clear_results()
            state.error = "Timed out waiting for job"
            yield _blank_ui(state, "Timed out waiting for the API job.", kind="err")
            return

        report = client.get_report(job.id)
        pages = client.get_pages(job.id)
        state.report = report
        state.pages = pages
        state.error = None

        opps = build_opportunities(report)
        state.opportunities = [
            {"kind": o.kind, "id": o.id, "title": o.title, "page_url": o.page_url}
            for o in opps
        ]

        vm = adapt_overview(report, mode=mode_key)
        page_rows = adapt_pages(pages)
        page_choices = [p.url for p in page_rows] or [str(report.get("base_url") or url)]
        selected = page_choices[0]
        state.selected_page_url = selected

        before, recs_md, after_md, evidence_md = detail_panels(report, selected)
        status_msg = "Analysis complete."
        if vm.crawl_partial:
            status_msg += " Partial crawl noted — see overview."

        yield (
            state,
            gr_update_status(status_msg, kind="ok"),
            overview_markdown(vm),
            opportunities_table(opps),
            pages_table(page_rows) if mode_key == "multi" else [],
            before,
            recs_md,
            after_md,
            evidence_md,
            gr.update(choices=page_choices, value=selected),
        )
    except AeoApiError as exc:
        state.clear_results()
        state.error = str(exc)
        code = f" (HTTP {exc.status_code})" if exc.status_code else ""
        yield _blank_ui(state, f"API error{code}: {exc}", kind="err")
    except Exception as exc:  # noqa: BLE001
        state.clear_results()
        state.error = str(exc)
        yield _blank_ui(state, f"Unexpected error: {exc}", kind="err")


def on_select_page(page_url: str | None, state: AnalysisState | None):
    state = state or AnalysisState()
    if not state.report or not page_url:
        return (
            state,
            EMPTY_DETAIL,
            "_No recommendations yet._",
            "_No after content yet._",
            "_No evidence yet._",
        )
    state.selected_page_url = page_url
    report = state.report
    page_id = None
    for p in adapt_pages(state.pages):
        if p.url == page_url:
            page_id = p.page_id
            break
    pi = report.get("page_intelligence") if isinstance(report.get("page_intelligence"), dict) else {}
    needs_opt = (
        bool(page_id)
        and bool(pi)
        and bool(pi.get("url"))
        and str(pi.get("url")).rstrip("/") != page_url.rstrip("/")
    )
    if needs_opt and state.job_id:
        try:
            opt = _client().content_optimization(
                job_id=state.job_id,
                page_id=page_id,
                content_draft=True,
            )
            report = merge_page_opt_into_report(report, opt)
        except (AeoApiError, OSError, Exception):  # noqa: BLE001 — UI must not crash on enrich
            pass
    before, recs_md, after_md, evidence_md = detail_panels(report, page_url)
    return state, before, recs_md, after_md, evidence_md


def on_select_opportunity(evt: Any, state: AnalysisState | None):
    """Dataframe select → jump to page detail.

    Gradio may call with (evt, state) or inject evt as the only event arg when
    wired via ``.select``; accept both.
    """
    # When Gradio passes only the event, ``state`` may actually be the event.
    if state is None or not isinstance(state, AnalysisState):
        if isinstance(evt, AnalysisState):
            state, evt = evt, None
        else:
            state = AnalysisState()
    state = state or AnalysisState()
    blank = (
        state,
        state.selected_page_url,
        EMPTY_DETAIL,
        "_No recommendations yet._",
        "_No after content yet._",
        "_No evidence yet._",
    )
    if not state.report or evt is None:
        return blank
    try:
        if hasattr(evt, "index"):
            idx = evt.index
            row_idx = int(idx[0] if isinstance(idx, (list, tuple)) else idx)
        else:
            row_idx = int(evt)
    except Exception:  # noqa: BLE001
        return blank
    if row_idx < 0 or row_idx >= len(state.opportunities):
        return blank
    page_url = state.opportunities[row_idx].get("page_url") or state.selected_page_url
    state, before, recs_md, after_md, evidence_md = on_select_page(page_url, state)
    return state, page_url, before, recs_md, after_md, evidence_md


def build_app():
    import gradio as gr

    with gr.Blocks(title="AEO Leadership Demo") as demo:
        state = gr.State(AnalysisState())

        gr.HTML(
            """
            <div id="aeo-brand">
              <div class="eyebrow">Answer Engine Optimization</div>
              <h1>AEO Leadership Demo</h1>
              <p class="subtitle">
                Paste a URL, run analysis, and follow the story from AEO Health → gaps →
                why → recommendations → recommended content — via the secured API only.
              </p>
            </div>
            """
        )

        with gr.Row():
            with gr.Column(scale=3, elem_classes=["aeo-panel"]):
                url_in = gr.Textbox(
                    label="Website URL",
                    placeholder="https://example.com/",
                    info="The UI never fetches this URL itself — only the secured AEO API does.",
                )
                mode_in = gr.Radio(
                    choices=[
                        "Single page URL",
                        "Multi-page crawl seed (same-host from seed)",
                    ],
                    value="Single page URL",
                    label="Analysis mode",
                    info="Multi-page is a same-host crawl from the seed — not a CMS series.",
                )
                draft_in = gr.Checkbox(
                    value=True,
                    label="Request optimization draft (deterministic skeleton when enabled)",
                    info="Drafts are generated suggestions — never a final optimized page.",
                )
                with gr.Row():
                    analyze_btn = gr.Button("Analyze", elem_id="analyze-btn")
                    demo_btn = gr.Button("▶ One-click demo", elem_id="demo-btn")
                    clear_btn = gr.Button("Clear", elem_id="clear-btn")
                    guide_btn = gr.Button("? How to read this report", elem_id="guide-btn")
            with gr.Column(scale=2, elem_classes=["aeo-panel"]):
                status_html = gr.HTML(value="")
                gr.Markdown(
                    f"**ⓘ Quick glossary**\n\n"
                    f"- {info_text('aeo_health')}\n"
                    f"- {info_text('ai_llm_visibility')}\n"
                    f"- {info_text('content_gap')}\n"
                    f"- {info_text('recommendation')}\n"
                    f"- {info_text('provenance')}"
                )

        with gr.Accordion("Guide & full glossary", open=False) as guide_acc:
            gr.Markdown(GUIDE_MARKDOWN + "\n\n" + all_terms_markdown())

        with gr.Row():
            with gr.Column(elem_classes=["aeo-panel"]):
                overview_md = gr.Markdown(EMPTY_OVERVIEW)

        with gr.Row():
            with gr.Column(elem_classes=["aeo-panel"]):
                gr.Markdown(
                    "### Biggest opportunities ⓘ\n" + info_text("optimization_opportunity")
                )
                opp_table = gr.Dataframe(
                    headers=OPP_HEADERS,
                    value=[],
                    interactive=False,
                    wrap=True,
                    label="Deterministic ranking from recommendations + high-severity gaps",
                )

        with gr.Row():
            with gr.Column(scale=1, elem_classes=["aeo-panel"]):
                gr.Markdown("### Pages")
                page_table = gr.Dataframe(
                    headers=PAGE_HEADERS,
                    value=[],
                    interactive=False,
                    wrap=True,
                    label="Crawled pages (multi-page mode)",
                )
                page_select = gr.Dropdown(
                    choices=[],
                    label="Inspect page",
                    info="Select a page for Before / Recommendations / After / Evidence.",
                )
            with gr.Column(scale=2, elem_classes=["aeo-panel"]):
                with gr.Tabs():
                    with gr.Tab("Before"):
                        before_md = gr.Markdown(EMPTY_DETAIL)
                    with gr.Tab("Recommendations"):
                        recs_md = gr.Markdown("_No recommendations yet._")
                    with gr.Tab("After"):
                        gr.Markdown(
                            "_After = optimization brief + recommended content/draft when "
                            "provided. Skeleton drafts are labeled honestly._"
                        )
                        after_md = gr.Markdown("_No after content yet._")
                    with gr.Tab("Evidence"):
                        evidence_md = gr.Markdown("_No evidence yet._")

        outputs = [
            state,
            status_html,
            overview_md,
            opp_table,
            page_table,
            before_md,
            recs_md,
            after_md,
            evidence_md,
            page_select,
        ]

        analyze_btn.click(
            fn=lambda u, m, d, s: run_analysis(u, m, False, d, s),
            inputs=[url_in, mode_in, draft_in, state],
            outputs=outputs,
        )
        demo_btn.click(
            fn=lambda m, d, s: run_analysis("https://demo.example/", m, True, d, s),
            inputs=[mode_in, draft_in, state],
            outputs=outputs,
        )

        def do_clear(s):
            s = clear_state(s)
            return (
                s,
                gr_update_status("Cleared.", kind="idle"),
                EMPTY_OVERVIEW,
                [],
                [],
                EMPTY_DETAIL,
                "_No recommendations yet._",
                "_No after content yet._",
                "_No evidence yet._",
                gr.update(choices=[], value=None),
                "",
            )

        clear_btn.click(
            fn=do_clear,
            inputs=[state],
            outputs=outputs + [url_in],
        )

        guide_btn.click(
            fn=lambda: gr.update(open=True),
            inputs=[],
            outputs=[guide_acc],
        )

        page_select.change(
            fn=on_select_page,
            inputs=[page_select, state],
            outputs=[state, before_md, recs_md, after_md, evidence_md],
        )

        opp_table.select(
            fn=on_select_opportunity,
            inputs=[state],
            outputs=[state, page_select, before_md, recs_md, after_md, evidence_md],
        )

        gr.Markdown(
            "<sub>Laptop/desktop optimized (1366×768+). Visibility metrics are sample "
            "estimates, not rankings. Drafts are never final optimized pages.</sub>"
        )

    return demo


def main() -> None:
    demo = build_app()
    host = os.environ.get("GRADIO_SERVER_NAME", "127.0.0.1")
    port = int(os.environ.get("GRADIO_SERVER_PORT", "7860"))
    theme = build_theme()
    demo.queue().launch(
        server_name=host,
        server_port=port,
        show_error=True,
        theme=theme,
        css=CUSTOM_CSS,
    )


if __name__ == "__main__":
    main()
