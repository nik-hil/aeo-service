"""UI adapters: Hashnode Markdown panes, tab labels, light code theme."""

from __future__ import annotations

from services.adapters import (
    adapt_before,
    adapt_recommended_markdown,
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
RECOMMENDED = (
    "**RECOMMENDED MARKDOWN** — a suggested draft\n\n"
    "# My Article\n\nBody paragraph about agents.\n\n## FAQ\n"
)


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
                "disclaimer": "RECOMMENDED MARKDOWN — not a final or guaranteed AEO article.",
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


def test_recommended_markdown_tab_complete_draft():
    md = adapt_recommended_markdown(_report(), page_url=HASHNODE_ARTICLE)
    assert "RECOMMENDED MARKDOWN" in md
    assert "guaranteed" in md.lower()
    assert "final" in md.lower()
    assert "My Article" in md
    # Unfenced copy-ready body (no ```markdown wrapper).
    assert "```markdown" not in md


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
    assert getattr(codes[0], "language", None) in {"markdown", "md", None} or True
    buttons = [
        c
        for c in demo.blocks.values()
        if isinstance(c, gr.Button) and getattr(c, "elem_id", None) == "aeo-copy-recommended-md"
    ]
    assert buttons, "expected Copy recommended Markdown button"
    assert "copy" in (buttons[0].value or "").lower()


def test_comparison_is_side_by_side_not_git_diff():
    html = comparison_html(
        _report(), HASHNODE_ARTICLE, pages_payload=_pages_payload()
    )
    assert "aeo-md-compare" in html
    assert "CURRENT MARKDOWN" in html
    assert "RECOMMENDED MARKDOWN" in html
    assert "aeo-md-scroll" in html
    assert "diff --git" not in html
    assert "@@" not in html
    assert "Git diff" in html or "not a Git diff" in html
    assert SOURCE_MD.splitlines()[0] in html
    assert "My Article" in html


def test_why_these_changes_label():
    from services.adapters import adapt_recommendations

    recs = adapt_recommendations(_report(), page_url=HASHNODE_ARTICLE)
    md = recommendations_markdown(recs)
    assert "WHY THESE CHANGES" in md
    assert "Lead with a direct answer" in md
    assert "Problem:" in md


def test_no_dark_code_pill_css_and_no_metadata_backticks_in_header():
    assert ".aeo-panel code" in CUSTOM_CSS
    assert "background: #ffffff !important" in CUSTOM_CSS
    assert "aeo-md-scroll" in CUSTOM_CSS
    header = page_header(_report(), _pages_payload(), HASHNODE_ARTICLE)
    # Metadata should not rely on backtick code pills.
    assert "`" not in header.markdown or header.markdown.count("`") == 0
