"""Focused Gradio UI tests: URL vs Markdown exclusivity + scroll config."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import app as gradio_app
import gradio as gr
import pytest


def _fake_report(*, title: str = "Fetched Title"):
    return SimpleNamespace(
        article=SimpleNamespace(
            title=title,
            section_headings=["H1"],
            intro="intro",
            target_domain="example.hashnode.dev",
            target_url="https://example.hashnode.dev/article",
        ),
        queries=SimpleNamespace(
            selected=[],
            candidates=[],
            quality_notes="",
        ),
        visibility=SimpleNamespace(
            provider="digitalocean_web_search",
            model="m",
            notes="OBSERVED",
            mention_rate=0.0,
            citation_rate=0.0,
            target_in_sources_rate=0.0,
            query_coverage=0.0,
            observations=[],
        ),
        recommendations=SimpleNamespace(
            opportunities=[],
            change_explanations=[],
            validation_warnings=[],
            source="llm_generated",
        ),
        quality_eval=None,
        current_markdown="# CURRENT from pipeline\n",
        recommended_markdown="# RECOMMENDED from pipeline\n",
        diff="(no diff)",
        summary_markdown="# Publish pack SUMMARY\n\nMock SUMMARY.\n",
        model="gpt",
        llm_used=False,
        retrieval_used=False,
        auto_publish=False,
    )


def test_resolve_both_empty_raises():
    with pytest.raises(ValueError, match="Provide Hashnode Markdown or a target"):
        gradio_app.resolve_content_source("", "")


def test_resolve_markdown_only():
    md, target, status = gradio_app.resolve_content_source("# Hello\n\nBody.\n", "")
    assert md.startswith("# Hello")
    assert target is None
    assert status == gradio_app.STATUS_MARKDOWN


def test_resolve_url_ignores_paste_and_fetches():
    calls: list[str] = []

    def fake_fetch(url: str) -> str:
        calls.append(url)
        return "# From URL\n\nFetched body.\n"

    paste = "# Leftover paste\n\nShould be ignored.\n"
    url = "https://example.hashnode.dev/my-article.md"
    md, target, status = gradio_app.resolve_content_source(
        paste, url, fetch_fn=fake_fetch
    )
    assert calls == [url]
    assert md.startswith("# From URL")
    assert "Leftover" not in md
    assert target == "https://example.hashnode.dev/my-article"
    assert status == gradio_app.STATUS_URL_IGNORES_PASTE


def test_resolve_url_without_paste():
    md, target, status = gradio_app.resolve_content_source(
        "",
        "https://example.hashnode.dev/a",
        fetch_fn=lambda u: f"# Fetched for {u}\n",
    )
    assert md.startswith("# Fetched for")
    assert target == "https://example.hashnode.dev/a"
    assert status == gradio_app.STATUS_URL


def test_resolve_url_fetch_failure_tells_user_to_paste_markdown():
    def boom(_url: str) -> str:
        raise ValueError("Failed to fetch target URL (403 for https://x.md).")

    with pytest.raises(ValueError, match="Unable to fetch Markdown") as excinfo:
        gradio_app.resolve_content_source(
            "",
            "https://example.hashnode.dev/post.md",
            fetch_fn=boom,
        )
    msg = str(excinfo.value)
    assert "Paste the Hashnode Markdown" in msg
    assert "clear the full article URL" in msg
    assert "403" in msg


def test_analyze_url_fetch_failure_surfaces_paste_guidance():
    def boom(_url: str) -> str:
        raise ValueError("Failed to fetch target URL (403 for https://x.md).")

    outs = gradio_app.analyze(
        "",
        "https://example.hashnode.dev/post.md",
        True,
        True,
        fetch_fn=boom,
    )
    assert "Unable to fetch Markdown" in outs[0]
    assert "Paste the Hashnode Markdown" in outs[0]
    assert "clear the full article URL" in outs[0]


def test_resolve_bare_domain_uses_paste():
    md, target, status = gradio_app.resolve_content_source(
        "# Paste\n", "example.com"
    )
    assert md == "# Paste"
    assert target == "example.com"
    assert status == gradio_app.STATUS_DOMAIN_AND_MARKDOWN


def test_resolve_bare_domain_without_markdown_errors():
    with pytest.raises(ValueError, match="Provide Hashnode Markdown"):
        gradio_app.resolve_content_source("", "example.com")


def test_analyze_url_with_leftover_markdown_uses_fetch_not_paste():
    pipeline = MagicMock(return_value=_fake_report(title="From URL"))
    fetched = "# Article from URL\n\nContent.\n"

    outs = gradio_app.analyze(
        "# Leftover example paste that must be ignored\n",
        "https://example.hashnode.dev/post.md",
        True,
        True,
        fetch_fn=lambda u: fetched,
        pipeline_fn=pipeline,
    )

    assert outs[0] == gradio_app.STATUS_URL_IGNORES_PASTE
    assert "From URL" in outs[1]
    assert "Mock SUMMARY" in outs[8]
    pipeline.assert_called_once()
    kwargs = pipeline.call_args.kwargs
    assert kwargs["text"] == fetched.strip()
    assert "Leftover" not in kwargs["text"]
    assert kwargs["target_domain"] == "https://example.hashnode.dev/post"
    assert kwargs["dry_run"] is True
    assert kwargs["skip_quality_eval"] is True


def test_analyze_markdown_only_still_works():
    pipeline = MagicMock(return_value=_fake_report(title="Paste Title"))
    paste = "# Only paste\n\nBody.\n"

    outs = gradio_app.analyze(
        paste, "", True, True, pipeline_fn=pipeline
    )

    assert outs[0] == gradio_app.STATUS_MARKDOWN
    pipeline.assert_called_once()
    assert pipeline.call_args.kwargs["text"] == paste.strip()
    assert pipeline.call_args.kwargs["target_domain"] is None


def test_analyze_logs_progress_to_stdout(capsys):
    pipeline = MagicMock(return_value=_fake_report(title="Paste Title"))
    paste = "# Only paste\n\nBody.\n"

    gradio_app.analyze(paste, "", True, True, pipeline_fn=pipeline)

    out = capsys.readouterr().out
    assert "[aeo] Analyze clicked" in out
    assert "content source resolved" in out
    assert "STATUS_MARKDOWN" not in out  # log human status text, not constant name
    assert "Using Hashnode Markdown paste" in out
    assert "pipeline starting" in out
    assert "Analyze done" in out


def test_analyze_both_empty_returns_error(capsys):
    outs = gradio_app.analyze("", "", True, False)
    assert "Error" in outs[0]
    assert "Provide Hashnode Markdown or a target" in outs[0]
    # Primary panels carry the same error (no silent success)
    assert "Error" in outs[1]
    logged = capsys.readouterr().out
    assert "[aeo] Analyze clicked" in logged
    assert "Analyze error (content source)" in logged


def test_fetch_markdown_from_url_prefers_md_suffix(monkeypatch):
    class FakeResp:
        def __init__(self, text: str, status_code: int = 200, content_type: str = "text/markdown"):
            self.text = text
            self.status_code = status_code
            self.headers = {"content-type": content_type}

    class FakeClient:
        def __init__(self, *a, **k):
            self.urls: list[str] = []

        def get(self, url, headers=None):
            self.urls.append(url)
            return FakeResp("# MD body\n")

        def close(self):
            return None

    client = FakeClient()
    text = gradio_app.fetch_markdown_from_url(
        "https://example.hashnode.dev/a.md", client=client
    )
    assert text.startswith("# MD body")
    assert client.urls == ["https://example.hashnode.dev/a.md"]


def test_build_app_scroll_config_and_css():
    demo = gradio_app.build_app()
    assert isinstance(demo, gr.Blocks)
    css = demo.css or ""
    assert "aeo-md-scroll" in css
    assert "overflow-y" in css
    assert "aeo-analyze-status" in css

    code_components = [
        c
        for c in demo.blocks.values()
        if isinstance(c, gr.Code)
    ]
    assert len(code_components) >= 4
    labels = {getattr(c, "label", None) for c in code_components}
    assert "SUMMARY.md" in labels
    for c in code_components:
        classes = c.elem_classes or []
        assert "aeo-md-scroll" in classes
        assert c.lines is not None and c.lines >= 16
        assert c.max_lines is not None and c.max_lines >= 16

    status = next(
        c
        for c in demo.blocks.values()
        if getattr(c, "elem_id", None) == "aeo-analyze-status"
    )
    assert "aeo-analyze-status" in (status.elem_classes or [])

    # Progress must stay on status next to Analyze — not on far-below outputs.
    analyze_fns = [
        fn
        for fn in demo.fns.values()
        if getattr(fn, "fn", None) is gradio_app.analyze
        or getattr(fn, "fn", None) == gradio_app.analyze
    ]
    assert analyze_fns, "expected Analyze click handler wired to analyze()"
    fn = analyze_fns[0]
    assert getattr(fn, "show_progress", None) == "full"
    progress_on = list(getattr(fn, "show_progress_on", None) or [])
    assert status in progress_on
    assert len(progress_on) == 1
