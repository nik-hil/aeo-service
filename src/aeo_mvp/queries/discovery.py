"""Query discovery orchestration (P1-C + Phase 3 query-discovery-v1).

Pipeline: understand → generate 30–50 → dedup/diversity → gate → select ~20.
Paid DO web_search is NEVER auto-run from discovery; requires explicit opt-in
after a ready QuerySet (see QuerySet.paid_retrieval_ready).
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from typing import Any, Literal

from aeo_mvp.queries.gate import GateDecision, gate_candidates
from aeo_mvp.queries.generate import CandidateQuery, generate_candidates
from aeo_mvp.queries.normalize import dedupe_by_text, normalize_query_text
from aeo_mvp.queries.select import (
    DEFAULT_TOP_K,
    MAX_TOP_K,
    MIN_TOP_K,
    QUERY_SET_VERSION,
    QuerySet,
    select_query_set,
)
from aeo_mvp.queries.store import query_set_summary
from aeo_mvp.understanding.profile import QUERY_DISCOVERY_METHOD
from aeo_mvp.understanding.site import SiteUnderstanding

# Legacy classification aliases kept for older report consumers
QueryClass = Literal[
    "brand",
    "informational",
    "problem_solution",
    "commercial",
    "comparison",
    "alternatives",
    "best_for",
    "product_service",
    "audience",
    "problem_solving",
    "recommendation",
    "navigational",
]

DEFAULT_TOP_N = DEFAULT_TOP_K  # Phase 3 default ~20
# Keep legacy bounds available
LEGACY_MIN_TOP_N = 8
LEGACY_MAX_TOP_N = 12

_INTENT_TO_LEGACY: dict[str, str] = {
    "informational": "informational",
    "problem_solving": "problem_solution",
    "comparison": "comparison",
    "recommendation": "best_for",
    "navigational": "brand",
    "commercial": "commercial",
}


@dataclass
class DiscoveredQuery:
    """Legacy prompt-shaped query (compat with demo/orchestrator)."""

    id: str
    query: str
    classification: str
    intent: str
    source: str = "site_understanding"
    score: float = 1.0
    topic: str | None = None
    entity: str | None = None
    rationale: str | None = None
    query_version: str | None = None
    source_evidence: list[dict[str, Any]] = field(default_factory=list)

    def to_prompt(self) -> dict[str, str]:
        return {"id": self.id, "query": self.query, "intent": self.intent}


@dataclass
class DiscoveryResult:
    queries: list[DiscoveredQuery] = field(default_factory=list)
    candidates_count: int = 0
    selected_count: int = 0
    accepted_count: int = 0
    rejected_count: int = 0
    method: str = QUERY_DISCOVERY_METHOD
    provenance: str = "derived_metric"
    fallback_used: bool = False
    query_set: dict[str, Any] = field(default_factory=dict)
    rejected_examples: list[dict[str, Any]] = field(default_factory=list)
    intent_breakdown: dict[str, int] = field(default_factory=dict)
    paid_retrieval_opt_in: bool = False
    paid_retrieval_ready: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "method": self.method,
            "provenance": self.provenance,
            "fallback_used": self.fallback_used,
            "candidates_count": self.candidates_count,
            "selected_count": self.selected_count,
            "accepted_count": self.accepted_count,
            "rejected_count": self.rejected_count,
            "queries": [asdict(q) for q in self.queries],
            "query_set": self.query_set,
            "rejected_examples": self.rejected_examples[:10],
            "intent_breakdown": self.intent_breakdown,
            "paid_retrieval_opt_in": self.paid_retrieval_opt_in,
            "paid_retrieval_ready": self.paid_retrieval_ready,
            "discovery_method": QUERY_DISCOVERY_METHOD,
            "query_set_version": QUERY_SET_VERSION,
        }

    def as_prompts(self) -> list[dict[str, str]]:
        return [q.to_prompt() for q in self.queries]


def _to_discovered(c: CandidateQuery) -> DiscoveredQuery:
    legacy = _INTENT_TO_LEGACY.get(c.intent, c.intent)
    return DiscoveredQuery(
        id=c.query_id,
        query=c.text,
        classification=legacy,
        intent=c.intent,
        source="query-discovery-v1",
        score=c.confidence,
        topic=c.topic,
        entity=c.entity,
        rationale=c.rationale,
        query_version=c.query_version,
        source_evidence=list(c.source_evidence),
    )


def dedupe_queries(candidates: list[DiscoveredQuery]) -> list[DiscoveredQuery]:
    return dedupe_by_text(
        candidates,
        text_fn=lambda q: q.query,
        score_fn=lambda q: q.score,
        id_fn=lambda q: q.id,
    )


def select_top_n(
    queries: list[DiscoveredQuery], top_n: int = DEFAULT_TOP_N
) -> list[DiscoveredQuery]:
    """Legacy helper — prefer select_query_set for Phase 3."""
    n = max(LEGACY_MIN_TOP_N, min(int(top_n), max(LEGACY_MAX_TOP_N, DEFAULT_TOP_K)))
    selected: list[DiscoveredQuery] = []
    used_classes: set[str] = set()
    remaining = list(queries)
    for q in list(remaining):
        if q.classification in used_classes:
            continue
        selected.append(q)
        used_classes.add(q.classification)
        remaining.remove(q)
        if len(selected) >= n:
            return selected[:n]
    for q in remaining:
        selected.append(q)
        if len(selected) >= n:
            break
    return selected[:n]


def discover_queries(
    understanding: SiteUnderstanding | None,
    *,
    top_n: int = DEFAULT_TOP_N,
    provenance: str = "derived_metric",
    selection_seed: int | None = None,
    paid_retrieval_opt_in: bool = False,
    target_site_audit: dict[str, Any] | None = None,
    min_candidates: int = 30,
    max_candidates: int = 50,
) -> DiscoveryResult:
    """Full Phase 3 discovery pipeline with legacy DiscoveryResult projection."""
    empty = not understanding or (
        not understanding.organization_brand
        and not understanding.products_services
        and not understanding.topics
    )
    if empty:
        return DiscoveryResult(
            queries=[],
            candidates_count=0,
            selected_count=0,
            provenance=provenance,
            fallback_used=True,
            paid_retrieval_opt_in=False,
            paid_retrieval_ready=False,
        )

    assert understanding is not None
    candidates = generate_candidates(
        understanding,
        min_candidates=min_candidates,
        max_candidates=max_candidates,
    )
    # Pre-dedupe exact/near before gate
    candidates = dedupe_by_text(
        candidates,
        text_fn=lambda q: q.text,
        score_fn=lambda q: q.confidence,
        id_fn=lambda q: q.query_id,
    )
    accepted, rejected = gate_candidates(candidates, understanding)
    qs = select_query_set(
        accepted,
        understanding=understanding,
        top_k=top_n,
        selection_seed=selection_seed,
        candidates_count=len(candidates),
        rejected_count=len(rejected),
        paid_retrieval_opt_in=paid_retrieval_opt_in,
        target_site_audit=target_site_audit,
    )

    discovered = [_to_discovered(m.query) for m in qs.members]
    rejected_examples = [
        {
            "query_id": q.query_id,
            "text": q.text,
            "intent": q.intent,
            "decision": d.to_dict(),
        }
        for q, d in rejected[:10]
    ]

    return DiscoveryResult(
        queries=discovered,
        candidates_count=len(candidates),
        selected_count=len(discovered),
        accepted_count=len(accepted),
        rejected_count=len(rejected),
        method=QUERY_DISCOVERY_METHOD,
        provenance=provenance,
        fallback_used=False,
        query_set=qs.to_dict(),
        rejected_examples=rejected_examples,
        intent_breakdown=dict(qs.intent_breakdown),
        paid_retrieval_opt_in=qs.paid_retrieval_opt_in,
        paid_retrieval_ready=qs.paid_retrieval_ready,
    )


def discovery_to_json(result: DiscoveryResult) -> str:
    return json.dumps(result.to_dict(), sort_keys=True)


# Re-exports for convenience
__all__ = [
    "DiscoveredQuery",
    "DiscoveryResult",
    "discover_queries",
    "dedupe_queries",
    "select_top_n",
    "discovery_to_json",
    "normalize_query_text",
    "DEFAULT_TOP_N",
    "MIN_TOP_N",
    "MAX_TOP_N",
    "QuerySet",
    "GateDecision",
    "CandidateQuery",
    "query_set_summary",
]

# Alias legacy names
MIN_TOP_N = MIN_TOP_K
MAX_TOP_N = MAX_TOP_K
