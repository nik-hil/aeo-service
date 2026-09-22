"""UI adapters: Hashnode Markdown panes, tab labels, light code theme."""

from __future__ import annotations

from services.adapters import (
    adapt_before,
    adapt_recommended_markdown,
    adapt_recommended_warnings_markdown,
    comparison_html,
    page_header,
    recommendations_markdown,
)
from styles.theme import CUSTOM_CSS


HASHNODE_MD = (
    "https://example.hashnode.dev/my-article.md"
)
HASHNODE_ARTICLE = "https://example.hashnode.dev/my-article"
SOURCE_MD = "# My Article\n\nBody paragraph about agents.\n"
RECOMMENDED = "# My Article\n\nBody paragraph about agents.\n\n## FAQ\n\n### What is an agent?\n\nAn agent plans and uses tools.\n"


def _pages_payload() -> dict:
    return {
        "pages": [
            {
                "id": "p1",
                "url": HASHNODE_ARTICLE,
                "title": "My Article",
                "depth": 0,
                "status_code": 200,
                "fetch_error": None,
                "source_url": HASHNODE_MD,
                "content_representation": "markdown",
                "canonical_url": HASHNODE_ARTICLE,
                "source_markdown": SOURCE_MD,
            }
        ]
    }


def _report() -> dict:
    return {
        "base_url": HASHNODE_ARTICLE,
        "page_intelligence": {
            "url": HASHNODE_ARTICLE,
            "title": "My Article",
            "word_count": 5,
            "content_representation": "markdown",
            "source_url": HASHNODE_MD,
            "canonical_url": HASHNODE_ARTICLE,
            "source_markdown": SOURCE_MD,
            "recommended_markdown": RECOMMENDED,
            "heading_outline": ["My Article"],
        },
        "content_drafts": [
            {
                "page_url": HASHNODE_ARTICLE,
                "status": "generated",
                "generator": "hashnode_recommended_markdown_v1",
                "content_provenance": "recommended_from_source_markdown",
                "body_markdown": RECOMMENDED,
                "disclaimer": "Suggested Markdown draft — review before publishing.",
                "warnings": ["insufficient_evidence_answer_first"],
            }
        ],
        "content_gaps": [
            {
                "page_url": HASHNODE_ARTICLE,
                "gaps": [
                    {
                        "gap_type": "answer_first",
                        "rationale": "Opening could answer the primary question sooner.",
                    }
                ],
            }
        ],
        "recommendations": [
            {
                "code": "REC_ADD_ANSWER_FIRST",
                "title": "Lead with a direct answer",
                "problem": "Weak opening",
                "why_it_matters": "Answer engines prefer clear leads",
                "recommended_action": "Edit opening in Hashnode editor",
                "effort": "S",
                "impact": 0.8,
                "affected_urls": [HASHNODE_ARTICLE],
                "evidence_snippets": ["opening is thin"],
            }
        ],
    }


def test_current_tab_shows_raw_markdown_and_metadata():
    before = adapt_before(
        _report(), page_url=HASHNODE_ARTICLE, pages_payload=_pages_payload()
    )
    assert "My Article" in before.markdown
    assert "Markdown" in before.markdown
    assert HASHNODE_MD in before.markdown
    assert HASHNODE_ARTICLE in before.markdown
    assert "Body paragraph about agents" in before.markdown
    assert "live browser" in before.markdown.lower()


def test_page_header_uses_real_title_not_untitled():
    header = page_header(_report(), _pages_payload(), HASHNODE_ARTICLE)
    assert header.title == "My Article"
    assert "(untitled)" not in header.title
    assert "(untitled)" not in header.html


def test_recommended_tab_body_paste_ready_no_disclaimer():
    md = adapt_recommended_markdown(_report(), page_url=HASHNODE_ARTICLE)
    assert "RECOMMENDED MARKDOWN" not in md
    assert "Suggested Markdown draft" not in md
    assert "guaranteed" not in md.lower()
    assert "review before publishing" not in md.lower()
    assert "My Article" in md
    assert "```markdown" not in md
    warn = adapt_recommended_warnings_markdown(_report(), page_url=HASHNODE_ARTICLE)
    assert "insufficient evidence answer first" in warn.lower() or "insufficient_evidence" in warn


def test_recommended_tab_label_is_recommended_not_markdown():
    """Visible tab / Code label must be exactly RECOMMENDED."""
    from app import build_app
    import gradio as gr

    demo = build_app()
    tabs = [
        c
        for c in demo.blocks.values()
        if isinstance(c, gr.Tab) and getattr(c, "label", None) in {
            "RECOMMENDED",
            "RECOMMENDED MARKDOWN",
        }
    ]
    assert any(getattr(t, "label", None) == "RECOMMENDED" for t in tabs)
    assert not any(getattr(t, "label", None) == "RECOMMENDED MARKDOWN" for t in tabs)
    codes = [
        c
        for c in demo.blocks.values()
        if isinstance(c, gr.Code) and getattr(c, "elem_id", None) == "aeo-recommended-markdown-code"
    ]
    assert codes
    assert getattr(codes[0], "label", None) == "RECOMMENDED"


def test_recommended_markdown_copy_control_in_app():
    """Copy control must exist for recommended MD (Code + Copy button)."""
    from app import build_app
    import gradio as gr

    demo = build_app()
    codes = [
        c
        for c in demo.blocks.values()
        if isinstance(c, gr.Code) and getattr(c, "elem_id", None) == "aeo-recommended-markdown-code"
    ]
    assert codes, "expected gr.Code for recommended Markdown"
    assert codes[0].interactive is False
    buttons = [
        c
        for c in demo.blocks.values()
        if isinstance(c, gr.Button) and getattr(c, "elem_id", None) == "aeo-copy-recommended-md"
    ]
    assert buttons, "expected Copy recommended Markdown button"
    assert "copy" in (buttons[0].value or "").lower()


def test_comparison_is_side_by_side_body_only_not_git_diff():
    html = comparison_html(
        _report(), HASHNODE_ARTICLE, pages_payload=_pages_payload()
    )
    assert "aeo-md-compare" in html
    assert "aeo-md-compare-grid" in html
    assert html.count("aeo-md-pane") >= 2
    assert "CURRENT" in html
    assert "RECOMMENDED" in html
    assert "RECOMMENDED MARKDOWN" not in html or html.count("RECOMMENDED") >= 1
    assert "aeo-md-scroll" in html
    # Structural: two body panes — not a unified git/patch diff UI.
    assert "diff --git" not in html
    assert "@@" not in html
    assert "<ins>" not in html
    assert "<del>" not in html
    assert SOURCE_MD.splitlines()[0] in html
    assert "My Article" in html
    # Disclaimers must not appear inside either document pane body.
    assert "**RECOMMENDED MARKDOWN**" not in html
    assert "guaranteed" not in html.lower() or "review before publishing" in html.lower()


def test_retired_compare_disclaimer_chrome_absent():
    """Helper/disclaimer chrome must stay out of app compare tab + comparison HTML."""
    from pathlib import Path

    app_src = Path(__file__).resolve().parents[1] / "app.py"
    app_text = app_src.read_text(encoding="utf-8")
    html = comparison_html(
        _report(), HASHNODE_ARTICLE, pages_payload=_pages_payload()
    )
    retired_everywhere = (
        "Side-by-side complete documents with independent scroll",
        "Recommended draft is a suggestion only",
        "Independent scroll panes — not a Git diff",
        "not a Git diff or patch view",
        "aeo-compare-note",
    )
    for needle in retired_everywhere:
        assert needle not in app_text, f"retired chrome still in app.py: {needle!r}"
        assert needle not in html, f"retired chrome still in comparison_html: {needle!r}"
    # Suggested-draft subtitle must not reappear as compare-pane chrome.
    assert "Suggested Markdown draft — review before publishing." not in html
    assert "aeo-md-compare-grid" in html
    assert html.count("aeo-md-pane") >= 2


def test_why_these_changes_structured_human_readable():
    from services.adapters import adapt_recommendations

    recs = adapt_recommendations(_report(), page_url=HASHNODE_ARTICLE)
    md = recommendations_markdown(recs)
    assert "WHY THESE CHANGES" in md
    assert "Lead with a direct answer" in md
    assert "**Problem:**" in md
    assert "**Why it matters:**" in md
    assert "**Recommended action:**" in md
    assert "**Effort:**" in md
    assert "**Impact:**" in md
    assert "**Affected page:**" in md
    assert f"[{HASHNODE_ARTICLE}]({HASHNODE_ARTICLE})" in md
    assert "**Evidence:**" in md
    assert "- opening is thin" in md
    # Never dump raw Python/JSON.
    assert "{'code'" not in md
    assert '"code":' not in md
    assert "None" not in md
    assert "null" not in md


def test_why_omits_missing_fields():
    from services.adapters import RecView, recommendations_markdown

    md = recommendations_markdown(
        [
            RecView(
                id="1",
                title="Only title",
                problem="",
                why="",
                action="Do the thing",
                effort="—",
                impact=None,
                evidence_snippets=[],
                affected_urls=[],
            )
        ]
    )
    assert "**Recommended action:** Do the thing" in md
    assert "**Problem:**" not in md
    assert "**Why it matters:**" not in md
    assert "**Effort:**" not in md
    assert "**Impact:**" not in md
    assert "**Affected page:**" not in md
    assert "**Evidence:**" not in md


def test_strips_legacy_disclaimer_from_stored_draft_body():
    report = _report()
    report["content_drafts"][0]["body_markdown"] = (
        "**RECOMMENDED MARKDOWN** — a suggested draft\n\n" + RECOMMENDED
    )
    md = adapt_recommended_markdown(report, page_url=HASHNODE_ARTICLE)
    assert not md.lstrip().startswith("**RECOMMENDED MARKDOWN**")
    assert "RECOMMENDED MARKDOWN" not in md.split("\n", 1)[0]
    assert "My Article" in md


def test_no_dark_code_pill_css_and_no_metadata_backticks_in_header():
    assert ".aeo-panel code" in CUSTOM_CSS
    assert "background: #ffffff !important" in CUSTOM_CSS
    assert "aeo-md-scroll" in CUSTOM_CSS
    header = page_header(_report(), _pages_payload(), HASHNODE_ARTICLE)
    assert "`" not in header.markdown or header.markdown.count("`") == 0
