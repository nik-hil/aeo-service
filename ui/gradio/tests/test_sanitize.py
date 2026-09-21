"""Update sanitize tests to use fixture_report module."""

from __future__ import annotations

from fixture_report import SAMPLE_REPORT, XSS_PAYLOAD
from services.adapters import adapt_before, adapt_draft, adapt_overview, overview_markdown
from services.sanitize import escape_text, looks_like_html, sanitize_code_block, strip_html_tags


def test_escape_text_neutralizes_tags():
    out = escape_text(XSS_PAYLOAD)
    assert "<script>" not in out
    assert "&lt;script&gt;" in out
    assert "<img" not in out


def test_code_block_and_before_escape():
    block = sanitize_code_block(XSS_PAYLOAD)
    assert block.startswith("```html")
    report = dict(SAMPLE_REPORT)
    report["page_intelligence"] = {
        **SAMPLE_REPORT["page_intelligence"],
        "title": XSS_PAYLOAD,
        "meta_description": XSS_PAYLOAD,
        "heading_outline": [XSS_PAYLOAD],
    }
    before = adapt_before(report)
    assert "<script>" not in before.markdown
    assert "&lt;script&gt;" in before.markdown


def test_draft_label_honest_for_skeleton():
    draft = adapt_draft(SAMPLE_REPORT)
    assert draft is not None
    assert "skeleton" in draft.label.lower()
    assert "final optimized" not in draft.label.lower()


def test_overview_escapes_caveats():
    report = dict(SAMPLE_REPORT)
    report["caveats"] = [XSS_PAYLOAD]
    vm = adapt_overview(report, mode="single")
    md = overview_markdown(vm)
    assert "<script>" not in md
    assert "&lt;script&gt;" in md


def test_strip_and_looks_like():
    assert looks_like_html(XSS_PAYLOAD)
    assert "Hello" in strip_html_tags("<b>Hello</b>")
