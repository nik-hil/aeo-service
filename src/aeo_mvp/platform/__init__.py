"""Platform capability adapters (minimal). Hashnode is the first adapter."""

from __future__ import annotations

from aeo_mvp.platform.hashnode.applicability import (
    HASHNODE_PLATFORM_MANAGED_CODES,
    RecommendationCategory,
    apply_hashnode_recommendation_filter,
    categorize_recommendation,
    is_hashnode_markdown_context,
)
from aeo_mvp.platform.hashnode.markdown_generator import (
    RecommendedMarkdown,
    generate_recommended_markdown,
)

__all__ = [
    "HASHNODE_PLATFORM_MANAGED_CODES",
    "RecommendationCategory",
    "RecommendedMarkdown",
    "apply_hashnode_recommendation_filter",
    "categorize_recommendation",
    "generate_recommended_markdown",
    "is_hashnode_markdown_context",
]
