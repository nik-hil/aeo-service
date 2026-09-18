"""Query discovery for LLM mention / AI-search experiments (Phase 3)."""

from aeo_mvp.queries.discovery import (
    DEFAULT_TOP_N,
    MAX_TOP_N,
    MIN_TOP_N,
    CandidateQuery,
    DiscoveryResult,
    DiscoveredQuery,
    GateDecision,
    QuerySet,
    discover_queries,
    discovery_to_json,
)
from aeo_mvp.queries.generate import generate_candidates
from aeo_mvp.queries.gate import gate_candidates
from aeo_mvp.queries.normalize import normalize_query_text
from aeo_mvp.queries.select import select_query_set
from aeo_mvp.queries.store import query_set_summary

__all__ = [
    "DiscoveryResult",
    "DiscoveredQuery",
    "discover_queries",
    "discovery_to_json",
    "CandidateQuery",
    "GateDecision",
    "QuerySet",
    "generate_candidates",
    "gate_candidates",
    "select_query_set",
    "normalize_query_text",
    "query_set_summary",
    "DEFAULT_TOP_N",
    "MIN_TOP_N",
    "MAX_TOP_N",
]
