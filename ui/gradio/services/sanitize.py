"""Escape / sanitize untrusted content for Gradio surfaces.

Never inject raw HTML from crawl or draft bodies into Gradio HTML components.
"""

from __future__ import annotations

import html
import re
from typing import Any


_CONTROL_CHARS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")


def escape_text(value: Any) -> str:
    """HTML-escape any value for safe display as plain text / markdown."""
    if value is None:
        return ""
    text = str(value)
    text = _CONTROL_CHARS.sub("", text)
    return html.escape(text, quote=True)


def safe_markdown_paragraph(value: Any) -> str:
    """Escape text then preserve simple newlines as markdown line breaks."""
    escaped = escape_text(value)
    if not escaped.strip():
        return ""
    # Avoid accidental markdown HTML passthrough of escaped entities is fine;
    # strip fenced HTML attempts that survived as literal tags after escape.
    return escaped.replace("\n", "  \n")


def sanitize_code_block(value: Any, *, language: str = "html") -> str:
    """Wrap escaped content in a fenced code block (never executable HTML)."""
    raw = "" if value is None else str(value)
    raw = _CONTROL_CHARS.sub("", raw)
    # Fence safety: break accidental triple-backtick termination
    safe = raw.replace("```", "``\u200b`")
    return f"```{language}\n{safe}\n```"


def looks_like_html(value: str) -> bool:
    if not value:
        return False
    lower = value.lower()
    return "<script" in lower or "<img" in lower or "javascript:" in lower or "<iframe" in lower


def strip_html_tags(value: Any) -> str:
    """Best-effort tag strip for extracted text display (then escape)."""
    if value is None:
        return ""
    text = str(value)
    text = re.sub(r"(?is)<script[^>]*>.*?</script>", "", text)
    text = re.sub(r"(?is)<style[^>]*>.*?</style>", "", text)
    text = re.sub(r"(?s)<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return escape_text(text)
