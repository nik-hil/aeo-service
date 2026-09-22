"""AEO Leadership Demo — Gradio application.

Presentation-only. All analysis goes through the secured AEO API.
Never fetches target URLs from the browser/UI process for crawling.

Page-select enrichment uses ``httpx.AsyncClient`` with selection tokens and a
session-scoped cache. Analyze job create and poll stay a synchronous generator.
The report is yielded before first-page enrichment, which then continues in that
same generator. Only page selection is an async generator.
"""

from __future__ import annotations

import asyncio
import logging
import os
import sys
import time
from pathlib import Path
from typing import Any, AsyncGenerator, Generator

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

from gradio import SelectData  # after unshadow; used by page-table select listener

from components.kpi_cards import kpi_cards_html
from glossary import GUIDE_MARKDOWN, all_terms_markdown, executive_glossary_markdown, info_text
from services.adapters import (
    UI_MULTI_MAX_PAGES,
    AnalysisState,
    adapt_before,
    adapt_evidence,
    adapt_overview,
    adapt_pages,
    adapt_question_opportunities,
    adapt_recommendations,
    adapt_recommended_markdown,
    adapt_recommended_warnings_markdown,
    comparison_html,
    enrichment_error_markdown,
    error_question_opportunities_markdown,
    loading_enrichment_markdown,
    loading_question_opportunities_markdown,
    merge_page_opt_into_report,
    overview_markdown,
    page_header,
    page_select_choices,
    page_url_from_choice,
    pages_table,
    question_copy_payloads,
    question_opportunities_markdown,
    recommendations_markdown,
)
from services.api_client import AeoApiClient, AeoApiError, user_safe_enrichment_error
from services.enrichment import (
    EnrichmentEntry,
    EnrichmentStatus,
    fetch_content_optimization,
    is_stale,
    needs_page_enrichment,
    next_selection_id,
    wait_for_terminal,
    wait_for_terminal_sync,
)
from services.opportunities import (
    build_opportunities,
    opportunities_table,
    resolve_opportunity_page_url,
)
from services.sanitize import escape_text
from styles.theme import CUSTOM_CSS, build_theme
from views.analyze import build_job_options

logger = logging.getLogger(__name__)

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
    "CURRENT → RECOMMENDED → CURRENT vs RECOMMENDED → Evidence → WHY THESE CHANGES "
    "→ AEO QUESTIONS & OPPORTUNITIES._"
)
EMPTY_RECS = "_No recommendation detail yet._"
EMPTY_BRIEF = ""
EMPTY_RECOMMENDED_META = "_Suggested Markdown draft — review before publishing._"
EMPTY_EVIDENCE = "_No evidence yet._"
EMPTY_COMPARE = (
    '<div class="aeo-md-compare">'
    "<p>Run analysis and select a page to compare CURRENT vs RECOMMENDED Markdown.</p>"
    "</div>"
)
EMPTY_HEADER = ""
EMPTY_QOA = (
    "### AEO QUESTIONS & OPPORTUNITIES\n\n"
    "_Select a page to analyze AEO questions._\n"
)
EMPTY_COPY = ""
OPP_HEADERS = ["#", "Kind", "Title", "Summary", "Page", "Signal"]
PAGE_HEADERS = ["Title", "URL", "Depth", "Status", "Error"]

AnalysisOutput = tuple[Any, ...]
DetailOutput = tuple[Any, ...]


def _empty_qoa_fields() -> tuple[Any, ...]:
    import gradio as gr

    return (
        EMPTY_QOA,
        EMPTY_COPY,
        EMPTY_COPY,
        EMPTY_COPY,
        gr.update(choices=[], value=None),
        "[]",
    )


def _qoa_fields_from_report(
    report: dict[str, Any] | None, page_url: str | None
) -> tuple[Any, ...]:
    import json

    import gradio as gr

    md = question_opportunities_markdown(report, page_url=page_url)
    cq, co, cc, per = question_copy_payloads(report, page_url=page_url)
    raw = adapt_question_opportunities(report, page_url=page_url)
    labels: list[str] = []
    for i, q in enumerate(raw.get("questions") or []):
        if not isinstance(q, dict):
            continue
        labels.append(f"{i + 1}. {str(q.get('question') or '')[:90]}")
    return (
        md,
        cq,
        co,
        cc,
        gr.update(choices=labels, value=labels[0] if labels else None),
        json.dumps(per),
    )


def _loading_qoa_fields() -> tuple[Any, ...]:
    import gradio as gr

    return (
        loading_question_opportunities_markdown(),
        EMPTY_COPY,
        EMPTY_COPY,
        EMPTY_COPY,
        gr.update(choices=[], value=None),
        "[]",
    )


def _error_qoa_fields(message: str) -> tuple[Any, ...]:
    import gradio as gr

    return (
        error_question_opportunities_markdown(message),
        EMPTY_COPY,
        EMPTY_COPY,
        EMPTY_COPY,
        gr.update(choices=[], value=None),
        "[]",
    )


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


def _page_id_for(state: AnalysisState, page_url: str | None) -> str | None:
    if not page_url:
        return None
    for p in adapt_pages(state.pages):
        if p.url == page_url or p.url.rstrip("/") == page_url.rstrip("/"):
            return p.page_id or None
    return None


def report_for_display(
    state: AnalysisState,
    page_url: str | None,
    page_id: str | None,
) -> dict[str, Any]:
    """Merge cached per-page enrichment for display without mutating shared report PI."""
    report = state.report or {}
    if not page_id or not state.job_id:
        return report
    entry = state.enrichment_cache.get(state.job_id, page_id)
    if entry and entry.status == EnrichmentStatus.SUCCESS and entry.payload:
        return merge_page_opt_into_report(report, entry.payload)
    return report


def _recommended_meta(report: dict[str, Any], page_url: str | None) -> str:
    """Subtitle + separate warnings for the RECOMMENDED tab (never in body)."""
    parts = [EMPTY_RECOMMENDED_META]
    warn = adapt_recommended_warnings_markdown(report, page_url=page_url)
    if warn:
        parts.extend(["", warn])
    return "\n".join(parts)


def detail_panels(
    report: dict[str, Any],
    page_url: str | None,
    *,
    pages_payload: dict[str, Any] | None = None,
) -> tuple[str, str, str, str, str]:
    """Return (CURRENT, WHY, RECOMMENDED body, Evidence, RECOMMENDED meta)."""
    before = adapt_before(report, page_url=page_url, pages_payload=pages_payload)
    recs = adapt_recommendations(report, page_url=page_url)
    recommended = adapt_recommended_markdown(report, page_url=page_url)
    evidence = adapt_evidence(report, page_url=page_url)
    return (
        before.markdown,
        recommendations_markdown(recs),
        recommended,
        evidence.markdown,
        _recommended_meta(report, page_url),
    )


def detail_qoa_fields(
    report: dict[str, Any] | None, page_url: str | None
) -> tuple[Any, ...]:
    """QOA markdown + copy payloads for Gradio outputs."""
    return _qoa_fields_from_report(report, page_url)


def _compare_panel(
    report: dict[str, Any],
    page_url: str | None,
    *,
    pages_payload: dict[str, Any] | None = None,
) -> str:
    return comparison_html(report, page_url, pages_payload=pages_payload)


def _blank_ui(state: AnalysisState, status: str, *, kind: str = "err") -> AnalysisOutput:
    import gradio as gr

    return (
        state,
        gr_update_status(status, kind=kind),
        kpi_cards_html(None),
        EMPTY_OVERVIEW,
        [],
        [],
        EMPTY_HEADER,
        EMPTY_DETAIL,
        EMPTY_RECS,
        EMPTY_BRIEF,
        EMPTY_RECOMMENDED_META,
        EMPTY_EVIDENCE,
        EMPTY_COMPARE,
        *_empty_qoa_fields(),
        gr.update(choices=[], value=None),
        gr.update(choices=[], value=None),
    )


def _loading_detail(state: AnalysisState, page_url: str) -> DetailOutput:
    base = state.report or {}
    header = page_header(base, state.pages, page_url)
    before_obs = adapt_before(
        base, page_url=page_url, pages_payload=state.pages
    ).markdown
    return (
        state,
        header.html,
        before_obs,
        loading_enrichment_markdown("WHY THESE CHANGES"),
        loading_enrichment_markdown("RECOMMENDED"),
        EMPTY_RECOMMENDED_META,
        loading_enrichment_markdown("Evidence"),
        (
            '<div class="aeo-md-compare"><p>'
            "Additional optimization analysis loading… "
            "Observed CURRENT Markdown stays visible while this loads."
            "</p></div>"
        ),
        *_loading_qoa_fields(),
    )


def _terminal_detail(
    state: AnalysisState, page_url: str, entry: EnrichmentEntry
) -> DetailOutput:
    base = state.report or {}
    header = page_header(base, state.pages, page_url)
    before_obs = adapt_before(
        base, page_url=page_url, pages_payload=state.pages
    ).markdown
    if entry.status == EnrichmentStatus.SUCCESS and entry.payload:
        display = merge_page_opt_into_report(base, entry.payload)
        before, recs_md, after_md, evidence_md, recommended_meta = detail_panels(
            display, page_url, pages_payload=state.pages
        )
        compare = _compare_panel(display, page_url, pages_payload=state.pages)
        header = page_header(display, state.pages, page_url)
        return (
            state,
            header.html,
            before,
            recs_md,
            after_md,
            recommended_meta,
            evidence_md,
            compare,
            *detail_qoa_fields(display, page_url),
        )
    err = entry.error_message or "Optimization analysis unavailable."
    before, _, _, _, _ = detail_panels(base, page_url, pages_payload=state.pages)
    return (
        state,
        header.html,
        before or before_obs,
        enrichment_error_markdown("WHY THESE CHANGES", err),
        enrichment_error_markdown("RECOMMENDED", err),
        EMPTY_RECOMMENDED_META,
        enrichment_error_markdown("Evidence", err),
        (
            f'<div class="aeo-md-compare"><p><strong>Could not load CURRENT vs RECOMMENDED:</strong> '
            f"{escape_text(err)}</p></div>"
        ),
        *_error_qoa_fields(err),
    )


def _analysis_output(
    state: AnalysisState,
    *,
    status_msg: str,
    vm: Any,
    opps: list[Any],
    page_rows: list[Any],
    mode_key: str,
    header_html: str,
    before: str,
    recs_md: str,
    after_md: str,
    recommended_meta: str,
    evidence_md: str,
    compare: str,
    page_choices: list[tuple[str, str]] | list[str],
    selected: str,
    qoa_fields: tuple[Any, ...] | None = None,
) -> AnalysisOutput:
    import gradio as gr

    qoa = qoa_fields if qoa_fields is not None else _empty_qoa_fields()
    return (
        state,
        gr_update_status(status_msg, kind="ok"),
        kpi_cards_html(vm),
        overview_markdown(vm),
        opportunities_table(opps),
        pages_table(page_rows) if page_rows else [],
        header_html,
        before,
        recs_md,
        after_md,
        recommended_meta,
        evidence_md,
        compare,
        *qoa,
        gr.update(choices=page_choices, value=selected),
        gr.update(choices=opportunity_choices(state), value=None),
    )


def run_analysis(
    url: str,
    mode: str,
    use_demo: bool,
    include_draft: bool,
    state: AnalysisState | None,
) -> Generator[AnalysisOutput, None, None]:
    """Clear stale results, create job, poll, adapt report.

    Analyze → create job → poll stays synchronous. When the first selected page
    still needs enrichment, the primary report and CURRENT (observed) signals
    are yielded before that fetch. Enrichment panels update on a later yield.
    """
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

    options = build_job_options(
        mode=mode_key, use_demo=use_demo, include_draft=include_draft
    )
    state.last_options = dict(options)
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

        vm = adapt_overview(report, mode=mode_key, opportunity_count=len(opps))
        page_rows = adapt_pages(pages)
        page_choices = page_select_choices(
            page_rows, fallback_url=str(report.get("base_url") or url)
        )
        selected = page_choices[0][1] if page_choices else str(report.get("base_url") or url)
        state.selected_page_url = selected
        state.selection_id = next_selection_id(state.selection_id)
        prefetch_selection = state.selection_id
        captured_job = state.job_id

        first_page_id = _page_id_for(state, selected)
        will_enrich = bool(
            first_page_id
            and captured_job
            and needs_page_enrichment(report, page_url=selected, page_id=first_page_id)
        )
        status_msg = "Analysis complete."
        if vm.crawl_partial:
            status_msg += " Partial crawl noted — see overview."

        header = page_header(report, pages, selected)
        if not will_enrich or not first_page_id or not captured_job:
            display = report_for_display(state, selected, first_page_id)
            before, recs_md, after_md, evidence_md, recommended_meta = detail_panels(
                display, selected, pages_payload=pages
            )
            yield _analysis_output(
                state,
                status_msg=status_msg,
                vm=vm,
                opps=opps,
                page_rows=page_rows,
                mode_key=mode_key,
                header_html=page_header(display, pages, selected).html,
                before=before,
                recs_md=recs_md,
                after_md=after_md,
                recommended_meta=recommended_meta,
                evidence_md=evidence_md,
                compare=_compare_panel(display, selected, pages_payload=pages),
                page_choices=page_choices,
                selected=selected,
                qoa_fields=detail_qoa_fields(display, selected),
            )
            return

        role, token = state.enrichment_cache.claim(captured_job, first_page_id)
        before_obs = adapt_before(report, page_url=selected, pages_payload=pages).markdown
        loading = _loading_detail(state, selected)
        yield _analysis_output(
            state,
            status_msg=status_msg,
            vm=vm,
            opps=opps,
            page_rows=page_rows,
            mode_key=mode_key,
            header_html=header.html,
            before=before_obs,
            recs_md=loading[3],
            after_md=loading[4],
            recommended_meta=loading[5],
            evidence_md=loading[6],
            compare=loading[7],
            page_choices=page_choices,
            selected=selected,
            qoa_fields=loading[8:14],
        )

        if role == "owner":
            stored = False
            try:
                try:
                    entry = asyncio.run(
                        fetch_content_optimization(
                            client,
                            job_id=captured_job,
                            page_id=first_page_id,
                            content_draft=True,
                        )
                    )
                except Exception as exc:  # noqa: BLE001
                    logger.exception("prefetch enrichment failed for first page")
                    entry = EnrichmentEntry(
                        status=EnrichmentStatus.ERROR,
                        error_message=user_safe_enrichment_error(exc),
                    )
                if state.job_id == captured_job:
                    state.enrichment_cache.set(captured_job, first_page_id, entry)
                    stored = True
            finally:
                if not stored:
                    state.enrichment_cache.pop_if_loading(captured_job, first_page_id, token)
        else:
            entry = (
                state.enrichment_cache.get(captured_job, first_page_id)
                if role == "settled"
                else wait_for_terminal_sync(state.enrichment_cache, captured_job, first_page_id)
            )
            if entry is None or entry.status == EnrichmentStatus.LOADING:
                entry = EnrichmentEntry(
                    status=EnrichmentStatus.ERROR,
                    error_message="Optimization analysis timed out. Page signals above remain valid.",
                )

        if state.job_id != captured_job or is_stale(state.selection_id, prefetch_selection):
            return
        if entry.status == EnrichmentStatus.SUCCESS and entry.payload:
            display = merge_page_opt_into_report(report, entry.payload)
            before, recs_md, after_md, evidence_md, recommended_meta = detail_panels(
                display, selected, pages_payload=pages
            )
            header = page_header(display, pages, selected)
            compare = _compare_panel(display, selected, pages_payload=pages)
        else:
            err = entry.error_message or "Optimization analysis unavailable."
            before, _, _, _, _ = detail_panels(report, selected, pages_payload=pages)
            before = before or before_obs
            recs_md = enrichment_error_markdown("WHY THESE CHANGES", err)
            after_md = enrichment_error_markdown("RECOMMENDED", err)
            recommended_meta = EMPTY_RECOMMENDED_META
            evidence_md = enrichment_error_markdown("Evidence", err)
            compare = (
                f'<div class="aeo-md-compare"><p><strong>Could not load CURRENT vs RECOMMENDED:</strong> '
                f"{escape_text(err)}</p></div>"
            )
            header = page_header(report, pages, selected)
        if entry.status == EnrichmentStatus.SUCCESS and entry.payload:
            qoa_fields = detail_qoa_fields(display, selected)
        else:
            qoa_fields = _error_qoa_fields(
                entry.error_message or "Optimization analysis unavailable."
            )
        yield _analysis_output(
            state,
            status_msg=status_msg,
            vm=vm,
            opps=opps,
            page_rows=page_rows,
            mode_key=mode_key,
            header_html=header.html,
            before=before,
            recs_md=recs_md,
            after_md=after_md,
            recommended_meta=recommended_meta,
            evidence_md=evidence_md,
            compare=compare,
            page_choices=page_choices,
            selected=selected,
            qoa_fields=qoa_fields,
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


def _empty_detail(state: AnalysisState) -> DetailOutput:
    return (
        state,
        EMPTY_HEADER,
        EMPTY_DETAIL,
        EMPTY_RECS,
        EMPTY_BRIEF,
        EMPTY_RECOMMENDED_META,
        EMPTY_EVIDENCE,
        EMPTY_COMPARE,
        *_empty_qoa_fields(),
    )


def _same_selected_page(state: AnalysisState, page_url: str, job_id: str) -> bool:
    """True when this session is still showing this job and page.

    A second select of the same page bumps ``selection_id`` but must not cancel
    the in-flight owner. A different page must not be overwritten.
    """
    if state.job_id != job_id:
        return False
    return (state.selected_page_url or "").rstrip("/") == (page_url or "").rstrip("/")


async def _owned_enrichment(
    state: AnalysisState, job_id: str, page_id: str, token: int | None
) -> EnrichmentEntry | None:
    """Fetch and store a terminal entry. Pop only this owner's LOADING marker."""
    stored = False
    try:
        entry = await fetch_content_optimization(
            _client(),
            job_id=job_id,
            page_id=page_id,
            content_draft=True,
        )
        if state.job_id != job_id:
            return None
        state.enrichment_cache.set(job_id, page_id, entry)
        stored = True
        return entry
    finally:
        if not stored:
            state.enrichment_cache.pop_if_loading(job_id, page_id, token)


async def on_select_page(
    page_url: str | None, state: AnalysisState | None
) -> AsyncGenerator[DetailOutput, None]:
    """Stage A: immediate identity + observed signals; Stage B: async enrichment.

    Uses a selection_id token so A→B→(A finishes late) cannot overwrite B.
    ``claim`` is atomic on this session cache: only one owner POSTs for a
    job_id+page_id. A concurrent handler waits for that owner's SUCCESS/ERROR.
    """
    state = state or AnalysisState()
    rows = adapt_pages(state.pages)
    page_url = page_url_from_choice(page_url, rows) or page_url
    if not state.report or not page_url:
        yield _empty_detail(state)
        return

    state.selection_id = next_selection_id(state.selection_id)
    state.selected_page_url = page_url
    page_id = _page_id_for(state, page_url)

    # Stage A — never blank the whole page.
    base = state.report
    header = page_header(base, state.pages, page_url)

    cached = (
        state.enrichment_cache.get(state.job_id, page_id)
        if state.job_id and page_id
        else None
    )

    if cached and cached.status == EnrichmentStatus.SUCCESS and cached.payload:
        display = merge_page_opt_into_report(base, cached.payload)
        before, recs_md, after_md, evidence_md, recommended_meta = detail_panels(
            display, page_url, pages_payload=state.pages
        )
        compare = _compare_panel(display, page_url, pages_payload=state.pages)
        header = page_header(display, state.pages, page_url)
        yield (
            state,
            header.html,
            before,
            recs_md,
            after_md,
            recommended_meta,
            evidence_md,
            compare,
            *detail_qoa_fields(display, page_url),
        )
        return

    if cached and cached.status == EnrichmentStatus.ERROR:
        # Prior failure — show observed + error; do not auto-retry forever.
        yield _terminal_detail(state, page_url, cached)
        return

    needs = needs_page_enrichment(base, page_url=page_url, page_id=page_id)
    if not needs or not state.job_id or not page_id:
        before, recs_md, after_md, evidence_md, recommended_meta = detail_panels(
            base, page_url, pages_payload=state.pages
        )
        compare = _compare_panel(base, page_url, pages_payload=state.pages)
        yield (
            state,
            header.html,
            before,
            recs_md,
            after_md,
            recommended_meta,
            evidence_md,
            compare,
            *detail_qoa_fields(base, page_url),
        )
        return

    job_id = state.job_id
    role, token = state.enrichment_cache.claim(job_id, page_id)
    if role == "settled":
        settled = state.enrichment_cache.get(job_id, page_id)
        if settled is not None:
            yield _terminal_detail(state, page_url, settled)
        else:
            before, recs_md, after_md, evidence_md, recommended_meta = detail_panels(
                base, page_url, pages_payload=state.pages
            )
            compare = _compare_panel(base, page_url, pages_payload=state.pages)
            yield (
                state,
                header.html,
                before,
                recs_md,
                after_md,
                recommended_meta,
                evidence_md,
                compare,
                *detail_qoa_fields(base, page_url),
            )
        return

    if role == "in_flight":
        yield _loading_detail(state, page_url)
        if not _same_selected_page(state, page_url, job_id):
            return
        entry = await wait_for_terminal(state.enrichment_cache, job_id, page_id)
        if not _same_selected_page(state, page_url, job_id):
            return
        if entry is None:
            # Owner dropped LOADING without a result. Become the owner once.
            role2, token2 = state.enrichment_cache.claim(job_id, page_id)
            if role2 == "owner":
                entry = await _owned_enrichment(state, job_id, page_id, token2)
            else:
                entry = await wait_for_terminal(state.enrichment_cache, job_id, page_id)
        if not _same_selected_page(state, page_url, job_id):
            return
        if entry is None or entry.status == EnrichmentStatus.LOADING:
            yield _terminal_detail(
                state,
                page_url,
                EnrichmentEntry(
                    status=EnrichmentStatus.ERROR,
                    error_message=(
                        "Optimization analysis timed out. Page signals above remain valid."
                    ),
                ),
            )
            return
        yield _terminal_detail(state, page_url, entry)
        return

    stored = False
    try:
        # LOADING is already claimed, so a concurrent select will not POST.
        yield _loading_detail(state, page_url)
        if state.job_id != job_id:
            return
        entry = await _owned_enrichment(state, job_id, page_id, token)
        stored = entry is not None
        if entry is None or not _same_selected_page(state, page_url, job_id):
            return
        yield _terminal_detail(state, page_url, entry)
    finally:
        if not stored:
            state.enrichment_cache.pop_if_loading(job_id, page_id, token)


async def on_select_opportunity_choice(
    choice: str | None, state: AnalysisState | None
) -> AsyncGenerator[tuple[Any, ...], None]:
    """Dropdown selection → page detail (reliable vs Dataframe.select quirks)."""
    state = state or AnalysisState()
    blank = (
        state,
        state.selected_page_url,
        EMPTY_HEADER,
        EMPTY_DETAIL,
        EMPTY_RECS,
        EMPTY_BRIEF,
        EMPTY_RECOMMENDED_META,
        EMPTY_EVIDENCE,
        EMPTY_COMPARE,
        *_empty_qoa_fields(),
    )
    if not state.report or not choice or not state.opportunities:
        yield blank
        return
    page_url = resolve_opportunity_page_url(
        state.opportunities, choice, fallback=state.selected_page_url
    )
    if not page_url:
        yield blank
        return
    async for out in on_select_page(page_url, state):
        # Prepend page_url for dropdown sync.
        yield (out[0], page_url, *out[1:])


async def on_page_table_select(
    evt: SelectData, state: AnalysisState | None
) -> AsyncGenerator[tuple[Any, ...], None]:
    """Table row select → sync Selected page dropdown + detail (same source of truth)."""
    state = state or AnalysisState()
    blank = (
        state,
        state.selected_page_url,
        EMPTY_HEADER,
        EMPTY_DETAIL,
        EMPTY_RECS,
        EMPTY_BRIEF,
        EMPTY_RECOMMENDED_META,
        EMPTY_EVIDENCE,
        EMPTY_COMPARE,
        *_empty_qoa_fields(),
    )
    rows = adapt_pages(state.pages)
    if not state.report or not rows:
        yield blank
        return
    idx = getattr(evt, "index", None)
    if isinstance(idx, (list, tuple)):
        row_idx = idx[0] if idx else None
    else:
        row_idx = idx
    try:
        row_idx = int(row_idx) if row_idx is not None else None
    except (TypeError, ValueError):
        row_idx = None
    if row_idx is None or row_idx < 0 or row_idx >= len(rows):
        yield blank
        return
    page_url = rows[row_idx].url
    async for out in on_select_page(page_url, state):
        yield (out[0], page_url, *out[1:])


def opportunity_choices(state: AnalysisState) -> list[str]:
    return [
        f"{i}. {o.get('title') or o.get('id') or 'opportunity'}"
        for i, o in enumerate(state.opportunities, start=1)
    ]


def build_app():
    import gradio as gr

    theme = build_theme()

    # Lock light color-scheme so Soft's OS-dark preference cannot paint near-white
    # ink onto white panels or dark dataframe headers.
    with gr.Blocks(
        title="AEO Leadership Demo",
        theme=theme,
        css=CUSTOM_CSS,
        head='<meta name="color-scheme" content="light">',
    ) as demo:
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
                    info=(
                        f"Multi-page requests up to {UI_MULTI_MAX_PAGES} same-host pages "
                        "(backend ceiling 25). Not a CMS series."
                    ),
                )
                draft_in = gr.Checkbox(
                    value=True,
                    label="Request optimization draft (deterministic skeleton when enabled)",
                    info="Drafts are generated suggestions — never a final optimized page.",
                )
                with gr.Row():
                    analyze_btn = gr.Button("Analyze", elem_id="analyze-btn", variant="primary")
                    demo_btn = gr.Button("▶ One-click demo", elem_id="demo-btn", variant="secondary")
                    clear_btn = gr.Button("Clear", elem_id="clear-btn", variant="secondary")
                    guide_btn = gr.Button("? How to read this report", elem_id="guide-btn", variant="secondary")
            with gr.Column(scale=2, elem_classes=["aeo-panel"]):
                status_html = gr.HTML(value="")
                gr.Markdown(executive_glossary_markdown())

        with gr.Accordion("Guide & technical glossary", open=False) as guide_acc:
            gr.Markdown(GUIDE_MARKDOWN + "\n\n" + all_terms_markdown())

        with gr.Row():
            with gr.Column(elem_classes=["aeo-panel"]):
                kpi_html = gr.HTML(value=kpi_cards_html(None))
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
                    column_widths=["48px", "120px", "22%", "28%", "22%", "10%"],
                )
                opp_select = gr.Dropdown(
                    choices=[],
                    label="Open opportunity page",
                    info="Select an opportunity to jump to its primary page detail.",
                )

        with gr.Column(elem_classes=["aeo-panel"], elem_id="aeo-page-workspace"):
            gr.Markdown("### Pages")
            page_table = gr.Dataframe(
                headers=PAGE_HEADERS,
                value=[],
                interactive=False,
                wrap=True,
                label=f"Crawled pages (multi-page; UI requests up to {UI_MULTI_MAX_PAGES})",
                column_widths=["22%", "38%", "10%", "12%", "18%"],
                elem_id="aeo-pages-table",
            )
            page_select = gr.Dropdown(
                choices=[],
                label="Selected page",
                info="Choose a crawled page to inspect.",
                elem_id="aeo-selected-page",
            )
            with gr.Column(elem_id="aeo-page-detail"):
                page_header_html = gr.HTML(value=EMPTY_HEADER)
                with gr.Tabs():
                    with gr.Tab("CURRENT"):
                        gr.Markdown(
                            "_Fetched Markdown or observed page signals — not a live browser render._"
                        )
                        before_md = gr.Markdown(EMPTY_DETAIL)
                    with gr.Tab("RECOMMENDED"):
                        recommended_meta = gr.Markdown(EMPTY_RECOMMENDED_META)
                        # Gradio Code has no show_copy_button in 5.x — Code + explicit Copy.
                        after_md = gr.Code(
                            value=EMPTY_BRIEF,
                            language="markdown",
                            interactive=False,
                            lines=22,
                            label="RECOMMENDED",
                            elem_id="aeo-recommended-markdown-code",
                        )
                        copy_recommended_btn = gr.Button(
                            "Copy recommended Markdown",
                            elem_id="aeo-copy-recommended-md",
                            variant="secondary",
                        )
                        copy_recommended_btn.click(
                            fn=None,
                            inputs=[after_md],
                            js=(
                                "(text) => { "
                                "navigator.clipboard.writeText(text ?? ''); "
                                "}"
                            ),
                        )
                    with gr.Tab("CURRENT vs RECOMMENDED"):
                        compare_md = gr.HTML(value=EMPTY_COMPARE)
                    with gr.Tab("Evidence"):
                        evidence_md = gr.Markdown(EMPTY_EVIDENCE)
                    with gr.Tab("WHY THESE CHANGES"):
                        gr.Markdown(
                            "_Recommendation detail (problem, why, action, effort, impact) — "
                            "audit / explanation, visually secondary._"
                        )
                        recs_md = gr.Markdown(EMPTY_RECS)
                    with gr.Tab("AEO QUESTIONS & OPPORTUNITIES"):
                        gr.Markdown(
                            "_Auto-generated AEO questions with answerability, evidence "
                            "validated against article text, and grounded proposed changes._"
                        )
                        qoa_md = gr.Markdown(EMPTY_QOA, elem_id="aeo-qoa-section")
                        with gr.Row():
                            copy_questions_btn = gr.Button(
                                "Copy Questions",
                                elem_id="aeo-copy-questions",
                                variant="secondary",
                            )
                            copy_opportunities_btn = gr.Button(
                                "Copy Opportunities",
                                elem_id="aeo-copy-opportunities",
                                variant="secondary",
                            )
                            copy_changes_btn = gr.Button(
                                "Copy Recommended Changes",
                                elem_id="aeo-copy-recommended-changes",
                                variant="secondary",
                            )
                        copy_feedback = gr.Markdown("", elem_id="aeo-qoa-copy-feedback")
                        copy_questions_text = gr.Textbox(
                            value=EMPTY_COPY,
                            visible=False,
                            elem_id="aeo-qoa-copy-questions-text",
                        )
                        copy_opportunities_text = gr.Textbox(
                            value=EMPTY_COPY,
                            visible=False,
                            elem_id="aeo-qoa-copy-opportunities-text",
                        )
                        copy_changes_text = gr.Textbox(
                            value=EMPTY_COPY,
                            visible=False,
                            elem_id="aeo-qoa-copy-changes-text",
                        )
                        per_question_dd = gr.Dropdown(
                            choices=[],
                            label="Per-question copy",
                            info="Select a question card, then Copy selected question.",
                            elem_id="aeo-qoa-per-question",
                        )
                        per_question_json = gr.Textbox(
                            value="[]",
                            visible=False,
                            elem_id="aeo-qoa-per-question-json",
                        )
                        copy_one_btn = gr.Button(
                            "Copy selected question",
                            elem_id="aeo-copy-one-question",
                            variant="secondary",
                        )

                        _CLIP_JS = (
                            "(text) => { "
                            "navigator.clipboard.writeText(text ?? ''); "
                            "return 'Copied'; "
                            "}"
                        )

                        def _copied_label(msg: str) -> str:
                            return f"**{msg}**" if msg else ""

                        copy_questions_btn.click(
                            fn=_copied_label,
                            inputs=[copy_questions_text],
                            outputs=[copy_feedback],
                            js=_CLIP_JS,
                        )
                        copy_opportunities_btn.click(
                            fn=_copied_label,
                            inputs=[copy_opportunities_text],
                            outputs=[copy_feedback],
                            js=_CLIP_JS,
                        )
                        copy_changes_btn.click(
                            fn=_copied_label,
                            inputs=[copy_changes_text],
                            outputs=[copy_feedback],
                            js=_CLIP_JS,
                        )

                        def _copy_selected_question(choice: str | None, payload: str) -> str:
                            import json

                            try:
                                items = json.loads(payload or "[]")
                            except json.JSONDecodeError:
                                return "**Copy failed**"
                            if not choice or not isinstance(items, list) or not items:
                                return "**Nothing to copy**"
                            try:
                                idx = int(str(choice).split(".", 1)[0]) - 1
                            except ValueError:
                                idx = 0
                            if idx < 0 or idx >= len(items):
                                return "**Nothing to copy**"
                            return "**Copied**"

                        copy_one_btn.click(
                            fn=_copy_selected_question,
                            inputs=[per_question_dd, per_question_json],
                            outputs=[copy_feedback],
                            js=(
                                "(choice, payload) => { "
                                "let items = []; "
                                "try { items = JSON.parse(payload || '[]'); } catch (e) { items = []; } "
                                "let idx = 0; "
                                "if (choice) { "
                                "  const n = parseInt(String(choice).split('.')[0], 10); "
                                "  if (!Number.isNaN(n) && n > 0) idx = n - 1; "
                                "} "
                                "const text = (items && items[idx]) ? items[idx] : ''; "
                                "navigator.clipboard.writeText(text); "
                                "return [choice, payload]; "
                                "}"
                            ),
                        )

        outputs = [
            state,
            status_html,
            kpi_html,
            overview_md,
            opp_table,
            page_table,
            page_header_html,
            before_md,
            recs_md,
            after_md,
            recommended_meta,
            evidence_md,
            compare_md,
            qoa_md,
            copy_questions_text,
            copy_opportunities_text,
            copy_changes_text,
            per_question_dd,
            per_question_json,
            page_select,
            opp_select,
        ]

        def analyze_click(u, m, d, s):
            yield from run_analysis(u, m, False, d, s)

        def demo_click(m, d, s):
            yield from run_analysis("https://demo.example/", m, True, d, s)

        analyze_btn.click(
            fn=analyze_click,
            inputs=[url_in, mode_in, draft_in, state],
            outputs=outputs,
        )
        demo_btn.click(
            fn=demo_click,
            inputs=[mode_in, draft_in, state],
            outputs=outputs,
        )

        def do_clear(s):
            s = clear_state(s)
            return (
                s,
                gr_update_status("Cleared.", kind="idle"),
                kpi_cards_html(None),
                EMPTY_OVERVIEW,
                [],
                [],
                EMPTY_HEADER,
                EMPTY_DETAIL,
                EMPTY_RECS,
                EMPTY_BRIEF,
                EMPTY_RECOMMENDED_META,
                EMPTY_EVIDENCE,
                EMPTY_COMPARE,
                *_empty_qoa_fields(),
                gr.update(choices=[], value=None),
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

        detail_outputs = [
            state,
            page_header_html,
            before_md,
            recs_md,
            after_md,
            recommended_meta,
            evidence_md,
            compare_md,
            qoa_md,
            copy_questions_text,
            copy_opportunities_text,
            copy_changes_text,
            per_question_dd,
            per_question_json,
        ]
        sync_outputs = [state, page_select, *detail_outputs[1:]]

        page_select.change(
            fn=on_select_page,
            inputs=[page_select, state],
            outputs=detail_outputs,
        )

        page_table.select(
            fn=on_page_table_select,
            inputs=[state],
            outputs=sync_outputs,
        )

        opp_select.change(
            fn=on_select_opportunity_choice,
            inputs=[opp_select, state],
            outputs=sync_outputs,
        )

        gr.Markdown(
            "<sub>Laptop/desktop optimized (1366×768+). Visibility metrics are sample "
            "estimates, not rankings. Drafts are never final optimized pages. "
            f"Multi-page UI request cap: {UI_MULTI_MAX_PAGES} (backend ceiling 25).</sub>"
        )

    # Bound concurrency for expensive work; do not disable the queue.
    return demo


def main() -> None:
    demo = build_app()
    host = os.environ.get("GRADIO_SERVER_NAME", "127.0.0.1")
    port = int(os.environ.get("GRADIO_SERVER_PORT", "7860"))
    demo.queue(default_concurrency_limit=4).launch(
        server_name=host, server_port=port, show_error=True
    )


if __name__ == "__main__":
    main()
