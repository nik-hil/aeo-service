"""Load and understand a Hashnode Markdown article."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from aeo_mvp.markdown import (
    Section,
    extract_front_matter,
    extract_intro,
    extract_title,
    parse_sections,
)


@dataclass
class Article:
    """Parsed Hashnode Markdown article (no CMS publish)."""

    source_path: str | None
    markdown: str
    title: str
    intro: str
    sections: list[Section]
    metadata: dict[str, str] = field(default_factory=dict)
    target_domain: str | None = None
    target_url: str | None = None
    brand_tokens: list[str] = field(default_factory=list)

    @property
    def section_headings(self) -> list[str]:
        return [s.heading for s in self.sections]

    def plain_text(self) -> str:
        parts = [self.title, self.intro]
        for s in self.sections:
            parts.append(s.heading)
            parts.append(s.body)
        return "\n\n".join(p for p in parts if p and p.strip())


def _absolute_http_url(value: str | None) -> str | None:
    """Return value only when it is an absolute http(s) URL (never invent from paths)."""
    if not value:
        return None
    cleaned = value.strip()
    if not cleaned.startswith(("http://", "https://")):
        return None
    return cleaned


def load_hashnode_markdown(
    path: str | Path | None = None,
    *,
    text: str | None = None,
    target_domain: str | None = None,
    target_url: str | None = None,
    brand_tokens: list[str] | None = None,
) -> Article:
    """Load Hashnode Markdown from a file path or raw string."""
    if text is None and path is None:
        raise ValueError("Provide path or text for Hashnode Markdown")
    source_path: str | None = None
    if text is None:
        p = Path(path)  # type: ignore[arg-type]
        markdown = p.read_text(encoding="utf-8")
        source_path = str(p)
    else:
        markdown = text
        source_path = str(path) if path else None

    sections = parse_sections(markdown)
    title = extract_title(markdown, sections)
    intro = extract_intro(markdown, sections)
    metadata = extract_front_matter(markdown)

    domain = target_domain or metadata.get("canonical_url") or metadata.get("url")
    if domain and "://" in domain:
        # Keep hostname-ish token for mention checks.
        from urllib.parse import urlparse

        host = urlparse(domain).hostname
        domain = host or domain

    # Exact article URL for page-level visibility (not derived from local path).
    page_url = _absolute_http_url(
        target_url or metadata.get("canonical_url") or metadata.get("url")
    )

    tokens = list(brand_tokens or [])
    if not tokens:
        # Derive light brand tokens from title words (skip stop-ish shorts).
        for w in title.replace(":", " ").replace("#", " ").split():
            clean = "".join(c for c in w if c.isalnum() or c in "-+")
            if len(clean) >= 4 and clean.lower() not in {
                "with",
                "from",
                "this",
                "that",
                "building",
                "using",
                "about",
            }:
                tokens.append(clean)
        tokens = tokens[:8]

    return Article(
        source_path=source_path,
        markdown=markdown,
        title=title,
        intro=intro,
        sections=sections,
        metadata=metadata,
        target_domain=domain,
        target_url=page_url,
        brand_tokens=tokens,
    )
