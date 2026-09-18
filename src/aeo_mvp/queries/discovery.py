"""Query discovery orchestration (P1-C + Phase 3 + Phase 4).

Phase 3: ``query-discovery-v1`` / ``query-set-v2``
Phase 4: ``query-discovery-v2`` / ``query-set-v3`` / ``query-quality-v1``

Paid DO web_search is NEVER auto-run from discovery; requires explicit opt-in
after a ready QuerySet. Dry-run / discovery_only stops before paid retrieval.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from typing import Any, Literal

from aeo_mvp.queries.gate import GateDecision as GateDecisionV1
from aeo_mvp.queries.gate import gate_candidates
from aeo_mvp.queries.generate import CandidateQuery, generate_candidates
from aeo_mvp.queries.generate_v2 import (
    DISCOVERY_METHOD_V2,
    GENERATOR,
    generate_candidates_v2,
)
from aeo_mvp.queries.normalize import (
    DEDUP_METHOD_LEXICAL,
    DEDUP_METHOD_SIMHASH,
    dedupe_by_text,
    normalize_query_text,
)
from aeo_mvp.queries.quality import (
    QUALITY_VERSION,
    GateDecision as GateDecisionV2,
    aggregate_set_diagnostics,
    gate_candidates_v2,
)
from aeo_mvp.queries.representativeness import build_representativeness_report
from aeo_mvp.queries.seed import resolve_seed
from aeo_mvp.queries.select import (
    DEFAULT_TOP_K,
    MAX_TOP_K,
    MIN_TOP_K,
    QUERY_SET_VERSION as QUERY_SET_VERSION_V2,
    QuerySet,
    select_query_set,
)
from aeo_mvp.queries.select_v2 import (
    QUERY_SET_VERSION as QUERY_SET_VERSION_V3,
    select_query_set_v2,
)
from aeo_mvp.queries.store import query_set_summary
from aeo_mvp.understanding.profile import QUERY_DISCOVERY_METHOD
from aeo_mvp.understanding.site import SiteUnderstanding

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

DEFAULT_TOP_N = DEFAULT_TOP_K
LEGACY_MIN_TOP_N = 8
LEGACY_MAX_TOP_N = 12

DiscoveryVersion = Literal["v1", "v2", "query-discovery-v1", "query-discovery-v2"]

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
    quality_diagnostics: dict[str, Any] | None = None
    generation_method: str | None = None

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
    # Phase 4 additive fields
    candidates: list[dict[str, Any]] = field(default_factory=list)
    gate_decisions: list[dict[str, Any]] = field(default_factory=list)
    rejected: list[dict[str, Any]] = field(default_factory=list)
    diagnostics: dict[str, Any] = field(default_factory=dict)
    representativeness: dict[str, Any] = field(default_factory=dict)
    seed_resolution: dict[str, Any] = field(default_factory=dict)
    discovery_only: bool = False
    grace_mode: bool = False
    content_hash: str | None = None
    fingerprint: str | None = None
    query_set_version: str = QUERY_SET_VERSION_V2
    quality_version: str | None = None

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
            "discovery_method": self.method,
            "query_set_version": self.query_set_version,
            "candidates": self.candidates,
            "gate_decisions": self.gate_decisions,
            "rejected": self.rejected,
            "diagnostics": self.diagnostics,
            "representativeness": self.representativeness,
            "seed_resolution": self.seed_resolution,
            "discovery_only": self.discovery_only,
            "grace_mode": self.grace_mode,
            "content_hash": self.content_hash,
            "fingerprint": self.fingerprint,
            "quality_version": self.quality_version,
        }

    def as_prompts(self) -> list[dict[str, str]]:
        return [q.to_prompt() for q in self.queries]


def _normalize_version(version: str | None) -> str:
    v = (version or "v2").strip().lower()
    if v in ("v1", "query-discovery-v1", "1"):
        return "v1"
    return "v2"


def _to_discovered(
    c: CandidateQuery,
    *,
    method: str,
    gate: GateDecisionV1 | GateDecisionV2 | None = None,
) -> DiscoveredQuery:
    legacy = _INTENT_TO_LEGACY.get(c.intent, c.intent)
    qd = None
    if gate is not None:
        qd = gate.to_dict()
    return DiscoveredQuery(
        id=c.query_id,
        query=c.text,
        classification=legacy,
        intent=c.intent,
        source=method,
        score=c.confidence,
        topic=c.topic,
        entity=c.entity,
        rationale=c.rationale,
        query_version=c.query_version,
        source_evidence=list(c.source_evidence),
        quality_diagnostics=qd,
        generation_method=c.generator,
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
    """Legacy helper — prefer select_query_set / select_query_set_v2."""
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
    selection_seed: int | str | None = None,
    paid_retrieval_opt_in: bool = False,
    target_site_audit: dict[str, Any] | None = None,
    min_candidates: int = 30,
    max_candidates: int = 50,
    options: dict[str, Any] | None = None,
    discovery_version: str | None = None,
    discovery_only: bool = False,
    semantic_dedup: str = "lexical",
    page_count: int | None = None,
    frozen_at: str | None = None,
) -> DiscoveryResult:
    """Discovery pipeline. Default Phase 4 ``v2``; pass ``discovery_version=v1`` for Phase 3."""
    opts = dict(options or {})
    version = _normalize_version(
        discovery_version or opts.get("query_discovery_version") or opts.get("discovery_version")
    )
    dry = bool(discovery_only or opts.get("discovery_only") or opts.get("dry_run"))
    # Paid never runs inside discovery; dry-run forces opt-in false for readiness honesty
    paid = False if dry else bool(paid_retrieval_opt_in)

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
            discovery_only=dry,
            method=DISCOVERY_METHOD_V2 if version == "v2" else QUERY_DISCOVERY_METHOD,
            query_set_version=QUERY_SET_VERSION_V3 if version == "v2" else QUERY_SET_VERSION_V2,
        )

    assert understanding is not None
    seed_res = resolve_seed(
        selection_seed=selection_seed,
        options=opts,
        evidence_hash=understanding.evidence_hash,
    )

    if version == "v1":
        return _discover_v1(
            understanding,
            top_n=top_n,
            provenance=provenance,
            seed_res=seed_res,
            paid_retrieval_opt_in=paid,
            target_site_audit=target_site_audit,
            min_candidates=min_candidates,
            max_candidates=max_candidates,
            discovery_only=dry,
        )

    return _discover_v2(
        understanding,
        top_n=top_n,
        provenance=provenance,
        seed_res=seed_res,
        paid_retrieval_opt_in=paid,
        target_site_audit=target_site_audit,
        min_candidates=min_candidates,
        max_candidates=max_candidates,
        discovery_only=dry,
        semantic_dedup=str(opts.get("semantic_dedup") or semantic_dedup),
        page_count=page_count,
        frozen_at=frozen_at,
        opts=opts,
    )


def _discover_v1(
    understanding: SiteUnderstanding,
    *,
    top_n: int,
    provenance: str,
    seed_res,
    paid_retrieval_opt_in: bool,
    target_site_audit: dict[str, Any] | None,
    min_candidates: int,
    max_candidates: int,
    discovery_only: bool,
) -> DiscoveryResult:
    candidates = generate_candidates(
        understanding,
        min_candidates=min_candidates,
        max_candidates=max_candidates,
    )
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
        selection_seed=seed_res.effective_seed,
        candidates_count=len(candidates),
        rejected_count=len(rejected),
        paid_retrieval_opt_in=paid_retrieval_opt_in,
        target_site_audit=target_site_audit,
    )
    # Annotate seed resolution onto query_set dict for audit (additive)
    qs_dict = qs.to_dict()
    qs_dict["root_seed"] = seed_res.root_seed
    qs_dict["effective_seed"] = seed_res.effective_seed
    qs_dict["seed_resolution"] = seed_res.to_dict()

    discovered = [_to_discovered(m.query, method=QUERY_DISCOVERY_METHOD) for m in qs.members]
    rejected_full = [
        {"query_id": q.query_id, "text": q.text, "intent": q.intent, "decision": d.to_dict()}
        for q, d in rejected
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
        query_set=qs_dict,
        rejected_examples=rejected_full[:10],
        intent_breakdown=dict(qs.intent_breakdown),
        paid_retrieval_opt_in=qs.paid_retrieval_opt_in,
        paid_retrieval_ready=qs.paid_retrieval_ready and not discovery_only,
        candidates=[c.to_dict() for c in candidates],
        gate_decisions=[d.to_dict() for _, d in accepted] + [d.to_dict() for _, d in rejected],
        rejected=rejected_full,
        seed_resolution=seed_res.to_dict(),
        discovery_only=discovery_only,
        query_set_version=QUERY_SET_VERSION_V2,
    )


def _discover_v2(
    understanding: SiteUnderstanding,
    *,
    top_n: int,
    provenance: str,
    seed_res,
    paid_retrieval_opt_in: bool,
    target_site_audit: dict[str, Any] | None,
    min_candidates: int,
    max_candidates: int,
    discovery_only: bool,
    semantic_dedup: str,
    page_count: int | None,
    frozen_at: str | None,
    opts: dict[str, Any],
) -> DiscoveryResult:
    candidates, plan = generate_candidates_v2(
        understanding,
        min_candidates=min_candidates,
        max_candidates=max_candidates,
        page_count=page_count,
    )
    dedup_method = (
        DEDUP_METHOD_SIMHASH
        if semantic_dedup in ("simhash", "simhash_v1")
        else DEDUP_METHOD_LEXICAL
    )
    candidates = dedupe_by_text(
        candidates,
        text_fn=lambda q: q.text,
        score_fn=lambda q: q.confidence,
        id_fn=lambda q: q.query_id,
        method=dedup_method,
    )
    accepted, rejected = gate_candidates_v2(candidates, understanding)
    mmr_lambda = float(opts.get("mmr_lambda", 0.65))
    max_per_topic = opts.get("max_per_topic")
    qs = select_query_set_v2(
        accepted,
        understanding=understanding,
        top_k=top_n,
        seed_resolution=seed_res,
        candidates_count=len(candidates),
        rejected_count=len(rejected),
        paid_retrieval_opt_in=paid_retrieval_opt_in,
        target_site_audit=target_site_audit,
        mmr_lambda=mmr_lambda,
        max_per_topic=int(max_per_topic) if max_per_topic is not None else None,
        grace_mode=plan.grace_mode,
        frozen_at=frozen_at,
        dedup_method=dedup_method,
    )
    report = build_representativeness_report(
        understanding=understanding,
        candidates=candidates,
        accepted=accepted,
        rejected=rejected,
        query_set=qs,
    )
    qs.representativeness = report
    qs.warnings = list(dict.fromkeys(list(qs.warnings) + list(plan.warnings)))

    gate_by_id = {m.query.query_id: m.gate for m in qs.members}
    discovered = [
        _to_discovered(
            m.query,
            method=DISCOVERY_METHOD_V2,
            gate=gate_by_id.get(m.query.query_id),
        )
        for m in qs.members
    ]
    rejected_full = [
        {
            "query_id": q.query_id,
            "text": q.text,
            "intent": q.intent,
            "topic": q.topic,
            "decision": d.to_dict(),
        }
        for q, d in rejected
    ]
    diagnostics = aggregate_set_diagnostics(
        selected_texts=[m.query.text for m in qs.members],
        rejected_count=len(rejected),
        accepted_count=len(accepted),
        intent_breakdown=qs.intent_breakdown,
        topic_breakdown=qs.topic_breakdown,
        fingerprint=qs.fingerprint,
    )

    return DiscoveryResult(
        queries=discovered,
        candidates_count=len(candidates),
        selected_count=len(discovered),
        accepted_count=len(accepted),
        rejected_count=len(rejected),
        method=DISCOVERY_METHOD_V2,
        provenance=provenance,
        fallback_used=False,
        query_set=qs.to_dict(),
        rejected_examples=rejected_full[:10],
        intent_breakdown=dict(qs.intent_breakdown),
        paid_retrieval_opt_in=qs.paid_retrieval_opt_in,
        paid_retrieval_ready=qs.paid_retrieval_ready and not discovery_only,
        candidates=[c.to_dict() for c in candidates],
        gate_decisions=[d.to_dict() for _, d in accepted]
        + [d.to_dict() for _, d in rejected],
        rejected=rejected_full,
        diagnostics=diagnostics,
        representativeness=report,
        seed_resolution=seed_res.to_dict(),
        discovery_only=discovery_only,
        grace_mode=plan.grace_mode,
        content_hash=qs.content_hash,
        fingerprint=qs.fingerprint,
        query_set_version=QUERY_SET_VERSION_V3,
        quality_version=QUALITY_VERSION,
    )


def discovery_to_json(result: DiscoveryResult) -> str:
    return json.dumps(result.to_dict(), sort_keys=True)


def replay_discovery_fingerprint(result: DiscoveryResult) -> str:
    """Canonical sha256 fingerprint shared with ``fingerprint_members``.

    Payload per member: query_id, text, intent, topic, entity.
    Prefer persisted fingerprint when present (same bytes).
    """
    from aeo_mvp.queries.select_v2 import (
        canonical_member_payload,
        fingerprint_from_payloads,
    )

    if result.fingerprint:
        # Recompute from ordered queries to prove shared canonical shape
        payloads = [
            canonical_member_payload(
                query_id=q.id,
                text=q.query,
                intent=q.intent,
                topic=q.topic,
                entity=q.entity,
            )
            for q in result.queries
        ]
        recomputed = fingerprint_from_payloads(payloads)
        # Persisted fingerprint must match canonical recompute
        if recomputed == result.fingerprint:
            return result.fingerprint
        return recomputed
    payloads = [
        canonical_member_payload(
            query_id=q.id,
            text=q.query,
            intent=q.intent,
            topic=q.topic,
            entity=q.entity,
        )
        for q in result.queries
    ]
    return fingerprint_from_payloads(payloads)


__all__ = [
    "DiscoveredQuery",
    "DiscoveryResult",
    "discover_queries",
    "dedupe_queries",
    "select_top_n",
    "discovery_to_json",
    "replay_discovery_fingerprint",
    "normalize_query_text",
    "DEFAULT_TOP_N",
    "MIN_TOP_N",
    "MAX_TOP_N",
    "QuerySet",
    "GateDecisionV1",
    "GateDecisionV2",
    "CandidateQuery",
    "query_set_summary",
    "DISCOVERY_METHOD_V2",
    "GENERATOR",
    "QUALITY_VERSION",
]

MIN_TOP_N = MIN_TOP_K
MAX_TOP_N = MAX_TOP_K
