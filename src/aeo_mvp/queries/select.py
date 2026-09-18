"""Deterministic stratified query selection (query-set-v2)."""

from __future__ import annotations

import hashlib
import random
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Literal

from aeo_mvp.queries.gate import GateDecision
from aeo_mvp.queries.generate import CandidateQuery, QueryIntent
from aeo_mvp.queries.normalize import dedupe_by_text, one_per_topic_intent
from aeo_mvp.understanding.profile import QUERY_DISCOVERY_METHOD
from aeo_mvp.understanding.site import SiteUnderstanding

QuerySetStatus = Literal["ready", "insufficient_evidence", "empty"]

DEFAULT_TOP_K = 20
MIN_TOP_K = 8
MAX_TOP_K = 30
QUERY_SET_VERSION = "query-set-v2"

# Intent strata targets for personal tech blogs / general
STRATA_ORDER: list[QueryIntent] = [
    "informational",
    "problem_solving",
    "recommendation",
    "comparison",
    "navigational",
    "commercial",
]


@dataclass
class QuerySetMember:
    query: CandidateQuery
    gate: GateDecision
    selection_rank: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "selection_rank": self.selection_rank,
            "query": self.query.to_dict(),
            "gate": self.gate.to_dict(),
        }


@dataclass
class QuerySet:
    query_set_id: str
    query_set_version: str
    selection_seed: int
    selection_method: str
    status: QuerySetStatus
    members: list[QuerySetMember] = field(default_factory=list)
    candidates_count: int = 0
    accepted_count: int = 0
    rejected_count: int = 0
    profile_snapshot: dict[str, Any] = field(default_factory=dict)
    target_site_audit: dict[str, Any] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    frozen_at: str | None = None
    discovery_method: str = QUERY_DISCOVERY_METHOD
    evidence_hash: str | None = None
    intent_breakdown: dict[str, int] = field(default_factory=dict)
    topic_breakdown: dict[str, int] = field(default_factory=dict)
    entity_breakdown: dict[str, int] = field(default_factory=dict)
    paid_retrieval_opt_in: bool = False
    paid_retrieval_ready: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "query_set_id": self.query_set_id,
            "query_set_version": self.query_set_version,
            "selection_seed": self.selection_seed,
            "selection_method": self.selection_method,
            "status": self.status,
            "members": [m.to_dict() for m in self.members],
            "candidates_count": self.candidates_count,
            "accepted_count": self.accepted_count,
            "rejected_count": self.rejected_count,
            "profile_snapshot": self.profile_snapshot,
            "target_site_audit": self.target_site_audit,
            "warnings": list(self.warnings),
            "frozen_at": self.frozen_at,
            "discovery_method": self.discovery_method,
            "evidence_hash": self.evidence_hash,
            "intent_breakdown": dict(self.intent_breakdown),
            "topic_breakdown": dict(self.topic_breakdown),
            "entity_breakdown": dict(self.entity_breakdown),
            "paid_retrieval_opt_in": self.paid_retrieval_opt_in,
            "paid_retrieval_ready": self.paid_retrieval_ready,
            "selected_count": len(self.members),
        }

    def as_prompts(self) -> list[dict[str, str]]:
        return [
            {
                "id": m.query.query_id,
                "query": m.query.text,
                "intent": m.query.intent,
            }
            for m in self.members
        ]


def _seed_from(evidence_hash: str | None, explicit: int | None) -> int:
    if explicit is not None:
        return int(explicit)
    raw = evidence_hash or "default"
    return int(hashlib.sha256(raw.encode()).hexdigest()[:8], 16)


def _set_id(seed: int, evidence_hash: str | None, version: str) -> str:
    h = hashlib.sha256(f"{seed}|{evidence_hash}|{version}".encode()).hexdigest()[:12]
    return f"qs_{h}"


def _breakdown(members: list[QuerySetMember]) -> tuple[dict[str, int], dict[str, int], dict[str, int]]:
    intents: dict[str, int] = {}
    topics: dict[str, int] = {}
    entities: dict[str, int] = {}
    for m in members:
        intents[m.query.intent] = intents.get(m.query.intent, 0) + 1
        t = m.query.topic or "_none"
        topics[t] = topics.get(t, 0) + 1
        e = m.query.entity or "_none"
        entities[e] = entities.get(e, 0) + 1
    return intents, topics, entities


def select_query_set(
    accepted: list[tuple[CandidateQuery, GateDecision]],
    *,
    understanding: SiteUnderstanding,
    top_k: int = DEFAULT_TOP_K,
    selection_seed: int | None = None,
    candidates_count: int = 0,
    rejected_count: int = 0,
    paid_retrieval_opt_in: bool = False,
    target_site_audit: dict[str, Any] | None = None,
) -> QuerySet:
    """Stratified deterministic selection from gated candidates."""
    k = max(MIN_TOP_K, min(int(top_k), MAX_TOP_K))
    seed = _seed_from(understanding.evidence_hash, selection_seed)
    warnings = list(understanding.warnings or [])

    if not accepted:
        return QuerySet(
            query_set_id=_set_id(seed, understanding.evidence_hash, QUERY_SET_VERSION),
            query_set_version=QUERY_SET_VERSION,
            selection_seed=seed,
            selection_method="stratified_intent_topic_v1",
            status="insufficient_evidence" if candidates_count else "empty",
            candidates_count=candidates_count,
            accepted_count=0,
            rejected_count=rejected_count,
            profile_snapshot=understanding.structured or {},
            target_site_audit=target_site_audit or {},
            warnings=warnings + ["no_accepted_candidates"],
            frozen_at=datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
            evidence_hash=understanding.evidence_hash,
            paid_retrieval_opt_in=False,
            paid_retrieval_ready=False,
        )

    # Dedupe + one-per (topic, intent)
    queries = [q for q, _ in accepted]
    gate_by_id = {q.query_id: g for q, g in accepted}
    deduped = dedupe_by_text(
        queries,
        text_fn=lambda q: q.text,
        score_fn=lambda q: q.confidence,
        id_fn=lambda q: q.query_id,
    )
    unique = one_per_topic_intent(
        deduped,
        topic_fn=lambda q: q.topic or "",
        intent_fn=lambda q: q.intent,
        score_fn=lambda q: q.confidence,
        id_fn=lambda q: q.query_id,
    )

    rng = random.Random(seed)
    by_intent: dict[str, list[CandidateQuery]] = {i: [] for i in STRATA_ORDER}
    for q in unique:
        by_intent.setdefault(q.intent, []).append(q)
    for intent, lst in by_intent.items():
        lst.sort(key=lambda q: (-q.confidence, q.query_id))
        # Stable shuffle within same confidence bands using seed
        rng.shuffle(lst)
        lst.sort(key=lambda q: (-q.confidence, q.query_id))

    selected: list[CandidateQuery] = []
    used_ids: set[str] = set()
    used_topics: set[str] = set()

    # Pass 1: round-robin strata
    progress = True
    while len(selected) < k and progress:
        progress = False
        for intent in STRATA_ORDER:
            if len(selected) >= k:
                break
            # Cap commercial for personal blogs
            if (
                understanding.site_genre == "personal_tech_blog"
                and intent == "commercial"
                and sum(1 for s in selected if s.intent == "commercial") >= max(1, k // 20)
            ):
                continue
            pool = [q for q in by_intent.get(intent, []) if q.query_id not in used_ids]
            if not pool:
                continue
            # Prefer new topics
            pool.sort(
                key=lambda q: (
                    0 if (q.topic or "") not in used_topics else 1,
                    -q.confidence,
                    q.query_id,
                )
            )
            pick = pool[0]
            selected.append(pick)
            used_ids.add(pick.query_id)
            if pick.topic:
                used_topics.add(pick.topic)
            progress = True

    # Pass 2: fill by confidence
    remaining = [q for q in unique if q.query_id not in used_ids]
    remaining.sort(key=lambda q: (-q.confidence, q.query_id))
    for q in remaining:
        if len(selected) >= k:
            break
        selected.append(q)
        used_ids.add(q.query_id)

    members = [
        QuerySetMember(query=q, gate=gate_by_id[q.query_id], selection_rank=i + 1)
        for i, q in enumerate(selected[:k])
    ]
    intents, topics, entities = _breakdown(members)

    # Paid retrieval requires explicit opt-in AND ready set — never auto
    ready = len(members) >= MIN_TOP_K
    return QuerySet(
        query_set_id=_set_id(seed, understanding.evidence_hash, QUERY_SET_VERSION),
        query_set_version=QUERY_SET_VERSION,
        selection_seed=seed,
        selection_method="stratified_intent_topic_v1",
        status="ready" if ready else "insufficient_evidence",
        members=members,
        candidates_count=candidates_count,
        accepted_count=len(accepted),
        rejected_count=rejected_count,
        profile_snapshot={
            "org_name": understanding.organization_brand,
            "site_genre": understanding.site_genre,
            "industry_category_guess": understanding.industry_category_guess,
            "topics_sample": understanding.topics[:8],
            "evidence_hash": understanding.evidence_hash,
            "structured_method": understanding.method,
        },
        target_site_audit=target_site_audit or {},
        warnings=warnings,
        frozen_at=datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        evidence_hash=understanding.evidence_hash,
        intent_breakdown=intents,
        topic_breakdown=topics,
        entity_breakdown=entities,
        paid_retrieval_opt_in=bool(paid_retrieval_opt_in),
        paid_retrieval_ready=bool(paid_retrieval_opt_in) and ready,
    )
