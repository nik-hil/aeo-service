"""Hashnode recommendation applicability filter.

Recommendation applicability = platform + representation.
Only actionable categories become prominent user-facing recommendations.
Generic analyzers still run; findings are filtered here before the UI.
"""

from __future__ import annotations

from enum import Enum
from typing import Any
from urllib.parse import urlparse

# Codes that assume author-controlled HTML/infra SEO — not actionable on Hashnode MD.
# Note: REC_ADD_META_DESCRIPTION is NOT managed — Hashnode exposes SEO description
# in article SEO settings (see capabilities.seo_description); remap to editor language.
HASHNODE_PLATFORM_MANAGED_CODES = frozenset(
    {
        "REC_FIX_ROBOTS_BLOCK",
        "REC_REMOVE_NOINDEX",
        "REC_ADD_CANONICAL",
        "REC_ADD_JSONLD_ORG",
        "REC_BROADEN_JSONLD_COVERAGE",
        "REC_ADD_TYPE_FIT_SCHEMA",
        "REC_FIX_JSONLD_PARSE",
        "REC_ADD_ORG_SIGNAL",
        "REC_ADD_CONTACT_OR_SAMEAS",
        "REC_REDUCE_JS_DEPENDENCY",
        "REC_FIX_HOME_HTTP",
    }
)

# Remap catalog copy to Hashnode editor field language (user_editable / content).
_HASHNODE_ACTION_REMAP: dict[str, dict[str, str]] = {
    "REC_IMPROVE_TITLE": {
        "title": "Clarify the article title (Hashnode editor)",
        "recommended_action": (
            "Edit the article title in the Hashnode editor so it clearly names "
            "the topic. Optionally set a distinct SEO title in Hashnode SEO settings."
        ),
        "problem": "Article title is weak or unclear for answer-engine extraction.",
    },
    "REC_ADD_META_DESCRIPTION": {
        "title": "Add an SEO description (Hashnode SEO settings)",
        "recommended_action": (
            "Set the SEO description in Hashnode article SEO settings "
            "(not a raw HTML meta tag)."
        ),
        "problem": "SEO description is missing or weak.",
    },
    "REC_ADD_ANSWER_FIRST": {
        "title": "Lead with a direct answer in the opening",
        "recommended_action": (
            "Rewrite the opening paragraphs in the Hashnode editor so the first "
            "screen answers the primary question directly."
        ),
    },
    "REC_ADD_FAQ_SECTION": {
        "title": "Add an FAQ section in Markdown",
        "recommended_action": (
            "Add a short FAQ section as Markdown headings + answers in the article "
            "body (GitHub publish / bulk import / editor)."
        ),
    },
    "REC_ADD_QUESTION_HEADINGS": {
        "title": "Add question-style headings in Markdown",
        "recommended_action": (
            "Add a few genuine who/what/how Markdown headings with direct answers beneath."
        ),
    },
    "REC_ADD_HOWTO_OR_STEPS": {
        "title": "Add a numbered steps section in Markdown",
        "recommended_action": (
            "Add an accurate ordered list (≥3 steps) in the article Markdown. "
            "Do not rely on HowTo JSON-LD — Hashnode manages structured data."
        ),
    },
    "REC_FIX_HEADING_HIERARCHY": {
        "title": "Fix Markdown heading hierarchy",
        "recommended_action": (
            "Use a single H1 title and nested ``##`` / ``###`` headings in the Markdown body."
        ),
    },
    "REC_EXPAND_THIN_CONTENT": {
        "title": "Expand thin sections in the article body",
        "recommended_action": (
            "Expand under-developed sections in the Hashnode editor / Markdown import "
            "with concrete explanations (do not invent unsupported facts)."
        ),
    },
    "REC_CLARIFY_BRAND_IN_COPY": {
        "title": "Clarify brand naming in article copy",
        "recommended_action": (
            "Use a consistent brand/product name in the title, subtitle, and opening copy."
        ),
    },
}


class RecommendationCategory(str, Enum):
    PLATFORM_MANAGED = "platform_managed"
    USER_EDITABLE = "user_editable"
    CONTENT_OPTIMIZATION = "content_optimization"
    INFORMATIONAL = "informational"


_CONTENT_CODES = frozenset(
    {
        "REC_IMPROVE_TITLE",
        "REC_ADD_ANSWER_FIRST",
        "REC_ADD_FAQ_SECTION",
        "REC_ADD_QUESTION_HEADINGS",
        "REC_ADD_HOWTO_OR_STEPS",
        "REC_FIX_HEADING_HIERARCHY",
        "REC_EXPAND_THIN_CONTENT",
        "REC_CLARIFY_BRAND_IN_COPY",
        "REC_IMPROVE_CITABLE_URLS",
        "REC_CONSOLIDATE_BRAND_NAME",
    }
)

_USER_EDITABLE_CODES = frozenset(
    {
        "REC_IMPROVE_TITLE",
        # Hashnode SEO settings — not raw HTML <meta>; remapped in _HASHNODE_ACTION_REMAP.
        "REC_ADD_META_DESCRIPTION",
    }
)


def is_hashnode_markdown_context(
    *,
    url: str | None = None,
    content_representation: str | None = None,
    source_url: str | None = None,
    adapter: str | None = None,
) -> bool:
    """True when recommendations should use Hashnode Markdown applicability rules."""
    if adapter == "hashnode" and (content_representation or "").lower() == "markdown":
        return True
    if (content_representation or "").lower() != "markdown":
        return False
    for candidate in (url, source_url):
        if not candidate:
            continue
        host = (urlparse(candidate).netloc or "").lower().strip(".").removeprefix("www.")
        if host.endswith(".hashnode.dev") and host != "hashnode.dev":
            return True
    return False


def categorize_recommendation(code: str) -> RecommendationCategory:
    if code in HASHNODE_PLATFORM_MANAGED_CODES:
        return RecommendationCategory.PLATFORM_MANAGED
    # Prefer user_editable over content_optimization when both apply (e.g. title / SEO).
    if code in _USER_EDITABLE_CODES:
        return RecommendationCategory.USER_EDITABLE
    if code in _CONTENT_CODES:
        return RecommendationCategory.CONTENT_OPTIMIZATION
    if code in ("REC_REVIEW_DEMO_ONLY",):
        return RecommendationCategory.INFORMATIONAL
    return RecommendationCategory.INFORMATIONAL


def _remap_hashnode_fields(rec: dict[str, Any]) -> dict[str, Any]:
    code = str(rec.get("code") or "")
    patch = _HASHNODE_ACTION_REMAP.get(code)
    if not patch:
        return rec
    out = dict(rec)
    out.update({k: v for k, v in patch.items() if v})
    out["platform"] = "hashnode"
    out["applicability_category"] = categorize_recommendation(code).value
    return out


def apply_hashnode_recommendation_filter(
    recommendations: list[dict[str, Any]],
    *,
    url: str | None = None,
    content_representation: str | None = None,
    source_url: str | None = None,
    include_informational: bool = False,
) -> list[dict[str, Any]]:
    """Filter/remap recommendations for a single Hashnode Markdown page context.

    Suppresses platform-managed infra/SEO HTML advice as actionable.
    Keeps content_optimization / user_editable items and remaps copy to
    Hashnode editor fields (e.g. SEO description, not ``<meta>`` tags).

    Canonical / Original URL is **not** promoted as a default actionable
    recommendation (only conditional when republishing — omitted unless
    explicitly present as a non-managed code).

    Callers with multi-page crawls should use
    ``filter_recommendations_page_scoped`` so non-Hashnode pages keep
    generic recommendation behavior.
    """
    if not is_hashnode_markdown_context(
        url=url,
        content_representation=content_representation,
        source_url=source_url,
    ):
        return list(recommendations)

    out: list[dict[str, Any]] = []
    for rec in recommendations:
        if not isinstance(rec, dict):
            continue
        code = str(rec.get("code") or "")
        category = categorize_recommendation(code)
        if category == RecommendationCategory.PLATFORM_MANAGED:
            # Drop from actionable list; callers may still inspect via category.
            continue
        if category == RecommendationCategory.INFORMATIONAL and not include_informational:
            continue
        out.append(_remap_hashnode_fields(rec))
    return out


def _normalize_page_url(url: str | None) -> str:
    return (url or "").strip().rstrip("/").lower()


def filter_recommendations_page_scoped(
    recommendations: list[dict[str, Any]],
    pages: list[Any],
    *,
    include_informational: bool = False,
) -> list[dict[str, Any]]:
    """Apply Hashnode filter only to recs associated with Hashnode Markdown pages.

    Non-Hashnode / non-MD / unrelated recommendations keep generic behavior.
    Site-level recommendations (no ``affected_urls``) are left unchanged even
    when the crawl also contains a Hashnode Markdown page.
    """
    hashnode_pages: list[Any] = []
    hashnode_url_index: dict[str, Any] = {}
    for page in pages or []:
        url = getattr(page, "url", None)
        if isinstance(page, dict):
            url = page.get("url")
            content_representation = page.get("content_representation")
            source_url = page.get("source_url")
        else:
            content_representation = getattr(page, "content_representation", None)
            source_url = getattr(page, "source_url", None)
        if not is_hashnode_markdown_context(
            url=url,
            content_representation=content_representation,
            source_url=source_url,
        ):
            continue
        hashnode_pages.append(page)
        for candidate in (url, source_url):
            key = _normalize_page_url(candidate)
            if key:
                hashnode_url_index[key] = page
                # Logical article URL for ``….md`` sources.
                if key.endswith(".md"):
                    hashnode_url_index[key[: -len(".md")]] = page

    if not hashnode_pages:
        return list(recommendations)

    out: list[dict[str, Any]] = []
    for rec in recommendations:
        if not isinstance(rec, dict):
            continue
        affected = [str(u) for u in (rec.get("affected_urls") or []) if u]
        if not affected:
            out.append(rec)
            continue
        matched_page = None
        for u in affected:
            matched_page = hashnode_url_index.get(_normalize_page_url(u))
            if matched_page is not None:
                break
        if matched_page is None:
            out.append(rec)
            continue
        if isinstance(matched_page, dict):
            filtered = apply_hashnode_recommendation_filter(
                [rec],
                url=matched_page.get("url"),
                content_representation=matched_page.get("content_representation"),
                source_url=matched_page.get("source_url"),
                include_informational=include_informational,
            )
        else:
            filtered = apply_hashnode_recommendation_filter(
                [rec],
                url=getattr(matched_page, "url", None),
                content_representation=getattr(
                    matched_page, "content_representation", None
                ),
                source_url=getattr(matched_page, "source_url", None),
                include_informational=include_informational,
            )
        out.extend(filtered)
    return out
