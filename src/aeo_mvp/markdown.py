"""Fence-aware ATX H1–H6 Markdown section parsing.

Headings inside fenced code blocks are ignored. Section body runs from the
line after a heading until the next same-or-higher-level heading (fewer or
equal ``#``), or EOF. H1 never swallows the whole article when H2+ exist.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

_HEADING_LINE_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$")
_FRONT_MATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n?", re.DOTALL)


@dataclass(frozen=True)
class Section:
    """One ATX section with deterministic boundaries."""

    heading: str
    level: int
    body: str
    heading_line_idx: int
    body_start_idx: int
    body_end_idx: int  # exclusive line index

    @property
    def marker(self) -> str:
        return "#" * self.level


def iter_atx_headings(lines: list[str]) -> list[tuple[int, int, str]]:
    """Return ``(line_idx, level, heading_text)`` for ATX headings outside fences."""
    heads: list[tuple[int, int, str]] = []
    in_fence = False
    for i, ln in enumerate(lines):
        stripped = ln.strip()
        if stripped.startswith("```"):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        m = _HEADING_LINE_RE.match(ln)
        if m:
            heads.append((i, len(m.group(1)), m.group(2).strip()))
    return heads


def parse_sections(markdown: str) -> list[Section]:
    """Deterministic H1–H6 sections (fence-aware)."""
    lines = (markdown or "").splitlines()
    heads = iter_atx_headings(lines)
    sections: list[Section] = []
    for k, (idx, level, heading) in enumerate(heads):
        end = len(lines)
        for j, lvl2, _h in heads[k + 1 :]:
            # Classic outline: end at same-or-higher level (fewer/equal #).
            # H1 special-case: also end at the first child heading so H1 is never
            # a mega-section corpus that swallows the whole article (AEO regression).
            if level == 1 or lvl2 <= level:
                end = j
                break
        body = "\n".join(lines[idx + 1 : end]).strip("\n")
        sections.append(
            Section(
                heading=heading,
                level=level,
                body=body,
                heading_line_idx=idx,
                body_start_idx=idx + 1,
                body_end_idx=end,
            )
        )
    return sections


def extract_title(markdown: str, sections: list[Section] | None = None) -> str:
    """First H1 title, else first heading, else first non-empty line."""
    secs = sections if sections is not None else parse_sections(markdown)
    for s in secs:
        if s.level == 1:
            return s.heading
    if secs:
        return secs[0].heading
    for ln in (markdown or "").splitlines():
        t = ln.strip()
        if t and not t.startswith("---") and not t.startswith("```"):
            return t[:120]
    return "Untitled"


def extract_intro(markdown: str, sections: list[Section] | None = None) -> str:
    """Text before the first heading, or H1 body until the next section."""
    lines = (markdown or "").splitlines()
    secs = sections if sections is not None else parse_sections(markdown)
    if not secs:
        return "\n".join(lines).strip()
    first = secs[0]
    preamble = "\n".join(lines[: first.heading_line_idx]).strip()
    # Strip YAML front matter from preamble for intro display.
    if preamble.startswith("---"):
        preamble = _FRONT_MATTER_RE.sub("", preamble + "\n", count=1).strip()
    if first.level == 1 and first.body.strip():
        # Intro = H1 body only (not the mega-corpus of all H2+).
        return first.body.strip()
    return preamble


def extract_front_matter(markdown: str) -> dict[str, str]:
    """Simple YAML-like front matter key: value pairs (no nested structures)."""
    text = markdown or ""
    m = _FRONT_MATTER_RE.match(text)
    if not m:
        return {}
    meta: dict[str, str] = {}
    for ln in m.group(1).splitlines():
        if ":" not in ln:
            continue
        key, _, val = ln.partition(":")
        key = key.strip()
        val = val.strip().strip("\"'")
        if key:
            meta[key] = val
    return meta


def find_section(sections: list[Section], heading: str) -> Section | None:
    """First section whose heading equals or contains ``heading`` (case-insensitive)."""
    want = (heading or "").strip().lower()
    if not want:
        return None
    for s in sections:
        title_l = s.heading.lower()
        if title_l == want or want in title_l:
            return s
    return None


def replace_section_body(markdown: str, heading: str, new_body: str) -> str:
    """Replace the body of the named section; leave other sections untouched."""
    lines = (markdown or "").splitlines()
    sections = parse_sections(markdown)
    target = find_section(sections, heading)
    if target is None:
        return markdown
    body_lines = (new_body or "").rstrip("\n").splitlines()
    out = (
        lines[: target.body_start_idx]
        + body_lines
        + lines[target.body_end_idx :]
    )
    return "\n".join(out) + ("\n" if markdown.endswith("\n") else "")


def append_under_heading(markdown: str, heading: str, addition: str) -> str:
    """Append ``addition`` to the end of a section body (before next heading)."""
    sections = parse_sections(markdown)
    target = find_section(sections, heading)
    if target is None:
        return markdown
    addition = (addition or "").strip()
    if not addition:
        return markdown
    existing = target.body.rstrip()
    new_body = f"{existing}\n\n{addition}" if existing else addition
    return replace_section_body(markdown, target.heading, new_body)
