"""Minimal Markdown → analyzable HTML normalization.

Used when a public ``.md`` alternate is fetched. Produces enough structure
(title, headings, paragraphs, links, lists) for the existing HTML analyzers.
Does **not** fabricate HTML-only signals (JSON-LD, meta robots, etc.).
"""

from __future__ import annotations

import html
import re
from dataclasses import dataclass

_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*)$")
_UL_RE = re.compile(r"^[-*+]\s+(.*)$")
_OL_RE = re.compile(r"^(\d+)\.\s+(.*)$")
_LINK_RE = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")
_BOLD_RE = re.compile(r"\*\*(.+?)\*\*")
_ITALIC_RE = re.compile(r"(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)")
_CODE_RE = re.compile(r"`([^`]+)`")
_FENCE_RE = re.compile(r"^```")


def _inline(text: str) -> str:
    """Escape then apply a tiny subset of inline Markdown (links, code, emphasis)."""
    parts: list[str] = []
    last = 0
    for m in _LINK_RE.finditer(text):
        parts.append(_inline_no_links(text[last : m.start()]))
        parts.append(
            f'<a href="{html.escape(m.group(2).strip(), quote=True)}">'
            f"{html.escape(m.group(1))}</a>"
        )
        last = m.end()
    parts.append(_inline_no_links(text[last:]))
    return "".join(parts)


def _inline_no_links(text: str) -> str:
    codes: list[str] = []

    def _code_sub(m: re.Match[str]) -> str:
        codes.append(html.escape(m.group(1)))
        return f"\x00C{len(codes) - 1}\x00"

    raw = _CODE_RE.sub(_code_sub, text)
    out = html.escape(raw)
    out = _BOLD_RE.sub(r"<strong>\1</strong>", out)
    out = _ITALIC_RE.sub(r"<em>\1</em>", out)
    for i, code in enumerate(codes):
        out = out.replace(f"\x00C{i}\x00", f"<code>{code}</code>")
    return out


@dataclass
class NormalizedMarkdown:
    html: str
    title: str | None
    representation: str = "markdown"


def markdown_to_analyzable_html(md: str) -> NormalizedMarkdown:
    """Convert Markdown text into a minimal HTML document for AEO analyzers."""
    lines = (md or "").replace("\r\n", "\n").replace("\r", "\n").split("\n")
    body: list[str] = []
    title: str | None = None
    para: list[str] = []
    list_kind: str | None = None
    list_items: list[str] = []
    in_fence = False
    fence_lines: list[str] = []

    def flush_para() -> None:
        nonlocal para
        if para:
            body.append(f"<p>{_inline(' '.join(para))}</p>")
            para = []

    def flush_list() -> None:
        nonlocal list_kind, list_items
        if list_kind and list_items:
            tag = "ul" if list_kind == "ul" else "ol"
            items = "".join(f"<li>{item}</li>" for item in list_items)
            body.append(f"<{tag}>{items}</{tag}>")
        list_kind = None
        list_items = []

    def flush_fence() -> None:
        nonlocal fence_lines
        if fence_lines:
            code = html.escape("\n".join(fence_lines))
            body.append(f"<pre><code>{code}</code></pre>")
            fence_lines = []

    for line in lines:
        if _FENCE_RE.match(line.strip()):
            if in_fence:
                flush_fence()
                in_fence = False
            else:
                flush_para()
                flush_list()
                in_fence = True
            continue
        if in_fence:
            fence_lines.append(line)
            continue

        if not line.strip():
            flush_para()
            flush_list()
            continue

        hm = _HEADING_RE.match(line)
        if hm:
            flush_para()
            flush_list()
            level = len(hm.group(1))
            text = hm.group(2).strip()
            if title is None and level == 1:
                title = text
            body.append(f"<h{level}>{_inline(text)}</h{level}>")
            continue

        um = _UL_RE.match(line)
        if um:
            flush_para()
            if list_kind not in (None, "ul"):
                flush_list()
            list_kind = "ul"
            list_items.append(_inline(um.group(1)))
            continue

        om = _OL_RE.match(line)
        if om:
            flush_para()
            if list_kind not in (None, "ol"):
                flush_list()
            list_kind = "ol"
            list_items.append(_inline(om.group(2)))
            continue

        flush_list()
        para.append(line.strip())

    flush_para()
    flush_list()
    if in_fence:
        flush_fence()

    if title is None:
        # Fallback: first non-empty line as title hint
        for line in lines:
            s = line.strip().lstrip("#").strip()
            if s:
                title = s[:200]
                break

    title_tag = html.escape(title) if title else ""
    doc = (
        "<!DOCTYPE html><html><head><meta charset=\"utf-8\"/>"
        f"<title>{title_tag}</title></head><body>\n"
        + "\n".join(body)
        + "\n</body></html>"
    )
    return NormalizedMarkdown(html=doc, title=title)
