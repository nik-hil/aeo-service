"""Shared fence-aware ATX H1–H6 section boundaries for Markdown.

Single parser used by grounded synthesis (corpus selection) and the Hashnode
Markdown generator (span replace). Section body runs from the line after a
heading until the next same-or-higher-level heading (fewer ``#``), or EOF.
Headings inside fenced code blocks are ignored.
"""

from __future__ import annotations

import re

_HEADING_LINE_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$")


def iter_atx_headings(lines: list[str]) -> list[tuple[int, int, str]]:
    """Return ``(line_idx, level, heading_text)`` for every ATX heading outside fences."""
    heads: list[tuple[int, int, str]] = []
    in_fence = False
    for i, ln in enumerate(lines):
        if ln.strip().startswith("```"):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        m = _HEADING_LINE_RE.match(ln)
        if m:
            heads.append((i, len(m.group(1)), m.group(2).strip()))
    return heads


def list_section_bodies(source_markdown: str) -> list[tuple[str, str, str]]:
    """Return ``[(heading, body, level_marker), ...]`` for every ATX section (H1–H6)."""
    lines = (source_markdown or "").splitlines()
    heads = iter_atx_headings(lines)
    sections: list[tuple[str, str, str]] = []
    for k, (idx, level, heading) in enumerate(heads):
        end = len(lines)
        for j, lvl2, _h in heads[k + 1 :]:
            if lvl2 <= level:
                end = j
                break
        body = "\n".join(lines[idx + 1 : end]).strip("\n")
        sections.append((heading, body, "#" * level))
    return sections


def find_section_span(
    md: str, heading: str
) -> tuple[int, int, int, str] | None:
    """Return ``(heading_line_idx, body_start_idx, body_end_idx, heading_line)``.

    Matches the first ATX heading whose title equals ``heading`` (case-insensitive)
    or contains it. Body end uses the same same-or-higher-level rule as
    ``list_section_bodies``.
    """
    lines = (md or "").splitlines()
    want = (heading or "").strip().lower()
    if not want:
        return None
    heads = iter_atx_headings(lines)
    for k, (idx, level, title) in enumerate(heads):
        title_l = title.lower()
        if title_l != want and want not in title_l:
            continue
        body_start = idx + 1
        body_end = len(lines)
        for j, lvl2, _h in heads[k + 1 :]:
            if lvl2 <= level:
                body_end = j
                break
        return idx, body_start, body_end, lines[idx]
    return None
