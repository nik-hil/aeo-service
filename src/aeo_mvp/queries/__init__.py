"""Query discovery for LLM mention / AI-search experiments (Phase 3 + Phase 4)."""

from aeo_mvp.queries.discovery import (
    DEFAULT_TOP_N,
    MAX_TOP_N,
    MIN_TOP_N,
    CandidateQuery,
    DiscoveryResult,
    DiscoveredQuery,
    QuerySet,
    discover_queries,
    discovery_to_json,
    replay_discovery_fingerprint,
)
from aeo_mvp.queries.gate import GateDecision, gate_candidates
from aeo_mvp.queries.generate import generate_candidates
from aeo_mvp.queries.generate_v2 import generate_candidates_v2
from aeo_mvp.queries.normalize import normalize_query_text
from aeo_mvp.queries.quality import gate_candidates_v2
from aeo_mvp.queries.select import select_query_set
from aeo_mvp.queries.select_v2 import select_query_set_v2
from aeo_mvp.queries.store import query_set_summary

__all__ = [
    "DiscoveryResult",
    "DiscoveredQuery",
    "discover_queries",
    "discovery_to_json",
    "replay_discovery_fingerprint",
    "CandidateQuery",
    "GateDecision",
    "QuerySet",
    "generate_candidates",
    "generate_candidates_v2",
    "gate_candidates",
    "gate_candidates_v2",
    "select_query_set",
    "select_query_set_v2",
    "normalize_query_text",
    "query_set_summary",
    "DEFAULT_TOP_N",
    "MIN_TOP_N",
    "MAX_TOP_N",
]
