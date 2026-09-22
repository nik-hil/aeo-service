"""Hashnode platform adapter — capabilities, applicability, Markdown drafts."""

from __future__ import annotations

from aeo_mvp.platform.hashnode.applicability import (
    HASHNODE_PLATFORM_MANAGED_CODES,
    RecommendationCategory,
    apply_hashnode_recommendation_filter,
    categorize_recommendation,
    filter_recommendations_page_scoped,
    is_hashnode_markdown_context,
)
from aeo_mvp.platform.hashnode.capabilities import HASHNODE_CAPABILITIES
from aeo_mvp.platform.hashnode.markdown_generator import (
    GENERATOR_VERSION,
    RecommendedMarkdown,
    SUGGESTED_MARKDOWN_SUBTITLE,
    generate_recommended_markdown,
)

__all__ = [
    "GENERATOR_VERSION",
    "HASHNODE_CAPABILITIES",
    "HASHNODE_PLATFORM_MANAGED_CODES",
    "RecommendationCategory",
    "RecommendedMarkdown",
    "SUGGESTED_MARKDOWN_SUBTITLE",
    "apply_hashnode_recommendation_filter",
    "categorize_recommendation",
    "filter_recommendations_page_scoped",
    "generate_recommended_markdown",
    "is_hashnode_markdown_context",
]
