"""Thin presentation helpers (Gradio-swappable later)."""

from __future__ import annotations

from glossary import info_text


def glossary_tip(key: str) -> str:
    return f"ⓘ {info_text(key)}"


def section_title(text: str, glossary_key: str | None = None) -> str:
    if glossary_key:
        return f"### {text} ⓘ\n{info_text(glossary_key)}"
    return f"### {text}"
