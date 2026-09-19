"""AI visibility experiment providers and metrics."""

from aeo_mvp.visibility.base import (
    AIVisibilityProvider,
    ProviderCapabilities,
    VisibilityContext,
    VisibilityObservation,
)
from aeo_mvp.visibility.competitors import extract_competitor_domains
from aeo_mvp.visibility.demo import DemoProvider
from aeo_mvp.visibility.digitalocean_web_search import (
    DigitalOceanWebSearchError,
    DigitalOceanWebSearchProvider,
)
from aeo_mvp.visibility.metrics import (
    aggregate_ai_search_metrics,
    aggregate_llm_metrics,
    aggregate_metrics,
    detect_citation,
    detect_mention,
    domain_matches_target,
    extract_urls,
)
from aeo_mvp.visibility.openai_compatible import (
    OpenAICompatibleError,
    OpenAICompatibleProvider,
)
from aeo_mvp.visibility.perplexity_sonar import PerplexitySonarProvider
from aeo_mvp.visibility.retrieval_base import (
    RETRIEVAL_REQUIRED_FIELDS,
    RetrievalEnabledVisibilityProvider,
    retrieval_capabilities,
)
from aeo_mvp.target_site import (
    MATCH_RULE_VERSION,
    TargetSiteIdentity,
    resolve_target_site_identity,
    site_key,
    target_match,
)

__all__ = [
    "AIVisibilityProvider",
    "ProviderCapabilities",
    "VisibilityContext",
    "VisibilityObservation",
    "DemoProvider",
    "DigitalOceanWebSearchError",
    "DigitalOceanWebSearchProvider",
    "OpenAICompatibleError",
    "OpenAICompatibleProvider",
    "PerplexitySonarProvider",
    "RetrievalEnabledVisibilityProvider",
    "RETRIEVAL_REQUIRED_FIELDS",
    "retrieval_capabilities",
    "extract_competitor_domains",
    "aggregate_metrics",
    "aggregate_llm_metrics",
    "aggregate_ai_search_metrics",
    "detect_mention",
    "detect_citation",
    "domain_matches_target",
    "extract_urls",
    "MATCH_RULE_VERSION",
    "TargetSiteIdentity",
    "resolve_target_site_identity",
    "site_key",
    "target_match",
]
