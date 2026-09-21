"""Guide accordion content."""

from __future__ import annotations

from glossary import GUIDE_MARKDOWN, all_terms_markdown


def guide_markdown() -> str:
    return GUIDE_MARKDOWN + "\n\n" + all_terms_markdown()
