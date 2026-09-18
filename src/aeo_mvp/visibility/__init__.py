"""AI visibility experiment providers and metrics."""

from aeo_mvp.visibility.base import (
    AIVisibilityProvider,
    VisibilityContext,
    VisibilityObservation,
)
from aeo_mvp.visibility.demo import DemoProvider
from aeo_mvp.visibility.metrics import (
    aggregate_metrics,
    detect_citation,
    detect_mention,
    extract_urls,
)
from aeo_mvp.visibility.openai_compatible import OpenAICompatibleProvider

__all__ = [
    "AIVisibilityProvider",
    "VisibilityContext",
    "VisibilityObservation",
    "DemoProvider",
    "OpenAICompatibleProvider",
    "aggregate_metrics",
    "detect_mention",
    "detect_citation",
    "extract_urls",
]
