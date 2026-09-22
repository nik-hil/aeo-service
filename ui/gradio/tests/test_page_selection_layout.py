"""Page selection layout: full-width workspace, Selected page dropdown."""

from __future__ import annotations

import gradio as gr
import pytest

from app import build_app, on_page_table_select, on_select_page
from fixture_report import PAGES_PAYLOAD, SAMPLE_REPORT
from services.adapters import (
    AnalysisState,
    PageRow,
    adapt_pages,
    page_select_choices,
    page_url_from_choice,
    pages_table,
)


def test_page_select_choices_prefer_title_url_fallback():
    rows = [
        PageRow(
            page_id="1",
            url="https://demo.example/",
            title="AcmeFlow Home",
            depth=0,
            status_code=200,
            fetch_error=None,
        ),
        PageRow(
            page_id="2",
            url="https://demo.example/untitled-path",
            title="",
            depth=1,
            status_code=200,
            fetch_error=None,
        ),
        PageRow(
            page_id="3",
            url="https://example.hashnode.dev/post",
            title="(untitled)",
            depth=0,
            status_code=200,
            fetch_error=None,
            content_representation="markdown",
            source_url="https://example.hashnode.dev/post.md",
        ),
    ]
    choices = page_select_choices(rows)
    assert choices[0] == ("AcmeFlow Home", "https://demo.example/")
    assert choices[1][0] == "https://demo.example/untitled-path"
    assert choices[1][1] == "https://demo.example/untitled-path"
    assert choices[2][0] == "https://example.hashnode.dev/post"
    assert page_url_from_choice("AcmeFlow Home", rows) == "https://demo.example/"
    assert page_url_from_choice("https://demo.example/", rows) == "https://demo.example/"


def test_page_select_choices_uniquify_duplicate_titles():
    rows = [
        PageRow("1", "https://a.example/one", "Same", 0, 200, None),
        PageRow("2", "https://a.example/two", "Same", 1, 200, None),
    ]
    choices = page_select_choices(rows)
    assert choices[0][0] == "Same"
    assert "Same (" in choices[1][0]
    assert choices[1][1] == "https://a.example/two"


def test_selected_page_selector_in_app_not_inspect_card():
    demo = build_app()
    dropdowns = [
        c
        for c in demo.blocks.values()
        if isinstance(c, gr.Dropdown)
        and getattr(c, "elem_id", None) == "aeo-selected-page"
    ]
    assert dropdowns, "expected Selected page dropdown"
    assert getattr(dropdowns[0], "label", None) == "Selected page"
    info = getattr(dropdowns[0], "info", None) or ""
    assert "Choose a crawled page to inspect." in info
    assert "CURRENT" not in info
    assert "RECOMMENDED" not in info

    inspect_labeled = [
        c
        for c in demo.blocks.values()
        if isinstance(c, gr.Dropdown) and getattr(c, "label", None) == "Inspect page"
    ]
    assert not inspect_labeled, "old Inspect page dropdown must be gone"

    # No large URL textbox for page inspection (analysis URL input remains).
    textboxes = [
        c
        for c in demo.blocks.values()
        if isinstance(c, gr.Textbox) and getattr(c, "label", None) == "Inspect page"
    ]
    assert not textboxes

    workspace = [
        c
        for c in demo.blocks.values()
        if getattr(c, "elem_id", None) == "aeo-page-workspace"
    ]
    assert workspace, "expected full-width #aeo-page-workspace"
    detail = [
        c
        for c in demo.blocks.values()
        if getattr(c, "elem_id", None) == "aeo-page-detail"
    ]
    assert detail, "expected #aeo-page-detail full-width region"
    table = [
        c
        for c in demo.blocks.values()
        if isinstance(c, gr.Dataframe) and getattr(c, "elem_id", None) == "aeo-pages-table"
    ]
    assert table, "expected crawled pages table"


def test_layout_css_full_width_no_side_split():
    from styles.theme import CUSTOM_CSS

    assert "#aeo-page-workspace" in CUSTOM_CSS
    assert "#aeo-selected-page" in CUSTOM_CSS
    assert "#aeo-page-detail" in CUSTOM_CSS
    assert "max-width: 28rem" in CUSTOM_CSS


@pytest.mark.asyncio
async def test_changing_selection_updates_detail():
    state = AnalysisState(
        job_id="job-demo-1",
        report=SAMPLE_REPORT,
        pages=PAGES_PAYLOAD,
        selected_page_url="https://demo.example/",
    )
    outs = []
    async for o in on_select_page("https://demo.example/about", state):
        outs.append(o)
    assert outs
    assert state.selected_page_url == "https://demo.example/about"
    assert "About" in (outs[-1][1] or "") or "about" in (outs[-1][1] or "").lower()


@pytest.mark.asyncio
async def test_table_select_syncs_dropdown_and_detail():
    state = AnalysisState(
        job_id="job-demo-1",
        report=SAMPLE_REPORT,
        pages=PAGES_PAYLOAD,
        selected_page_url="https://demo.example/",
    )
    rows = adapt_pages(PAGES_PAYLOAD)
    about_idx = next(i for i, r in enumerate(rows) if r.url.rstrip("/").endswith("/about"))

    class _Evt:
        index = (about_idx, 0)

    outs = []
    async for o in on_page_table_select(_Evt(), state):
        outs.append(o)
    assert outs
    # sync tuple: state, page_select value, header, ...
    assert outs[-1][1] == "https://demo.example/about"
    assert state.selected_page_url == "https://demo.example/about"
    assert outs[-1][2]  # header html


def test_pages_table_still_has_core_columns():
    rows = adapt_pages(PAGES_PAYLOAD)
    table = pages_table(rows)
    assert table
    assert len(table[0]) == 5
    choices = page_select_choices(rows)
    assert all(isinstance(c, tuple) and len(c) == 2 for c in choices)
    labels = [label for label, _ in choices]
    assert "Home" in labels
    assert "About" in labels
    assert all(url.startswith("https://") for _, url in choices)
