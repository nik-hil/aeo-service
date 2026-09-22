"""Verified Hashnode author-facing capabilities (do not invent beyond this).

Hashnode facts used by the AEO surface:
- Official public ``.md`` representation for article pages on ``*.hashnode.dev``
- Editor fields: title, content, subtitle
- SEO title + SEO description
- Series membership
- Markdown via GitHub publish / bulk import
- Platform manages much SEO / structured data / HTML canonical for normal articles

Authors generally cannot control via the article editor:
- Organization / homepage / arbitrary schema.org JSON-LD
- Raw HTML ``<meta>`` tags or HTML ``rel=canonical``
- robots.txt / sitemap / HTTP response headers
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class HashnodeCapabilities:
    """Capability boundary for Hashnode articles (representation-aware)."""

    adapter: str = "hashnode"
    official_markdown_twin: bool = True
    editor_title: bool = True
    editor_content: bool = True
    editor_subtitle: bool = True
    seo_title: bool = True
    seo_description: bool = True
    series: bool = True
    markdown_github_publish: bool = True
    markdown_bulk_import: bool = True
    # Platform-managed for normal articles — not user-actionable HTML SEO.
    platform_manages_jsonld: bool = True
    platform_manages_html_meta: bool = True
    platform_manages_html_canonical: bool = True
    platform_manages_robots_sitemap_headers: bool = True
    # Conditional: Original URL / republishing facility only when relevant.
    conditional_original_url: bool = True


HASHNODE_CAPABILITIES = HashnodeCapabilities()
