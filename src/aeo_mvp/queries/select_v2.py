"""Coverage-aware query selection ``query-set-v3`` (Phase 4).

Pipeline: intent budgets → coverage cell fill → lexical MMR → max-per-topic caps.
Deterministic given effective_seed + candidate pool.
"""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass, field
from typing import Any, Literal

from aeo_mvp.queries.generate import CandidateQuery
from aeo_mvp.queries.intent_budget import (
    INTENT_BUDGET_ID,
    STRATA_ORDER,
    IntentBudgetPolicy,
    build_intent_budget_policy,
)
from aeo_mvp.queries.normalize import jaccard, tokenize
from aeo_mvp.queries.quality import GateDecision, QUALITY_VERSION
from aeo_mvp.queries.seed import SeedResolution
from aeo_mvp.understanding.profile import QUERY_DISCOVERY_METHOD
from aeo_mvp.understanding.site import SiteUnderstanding

QuerySetStatus = Literal["ready", "insufficient_evidence", "empty"]

DEFAULT_TOP_K = 20
MIN_TOP_K = 8
MAX_TOP_K = 30
QUERY_SET_VERSION = "query-set-v3"
SELECTION_METHOD = "coverage_mmr_intent_budget_v1"
DISCOVERY_METHOD_V2 = "query-discovery-v2"
DEFAULT_MMR_LAMBDA = 0.65
DEFAULT_MAX_PER_TOPIC = 3


@dataclass
class QuerySetMember:
    query: CandidateQuery
    gate: GateDecision
    selection_rank: int
    selection_rationale: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "selection_rank": self.selection_rank,
            "selection_rationale": self.selection_rationale,
            "query": self.query.to_dict(),
            "gate": self.gate.to_dict(),
        }


@dataclass
class QuerySetV3:
    query_set_id: str
    query_set_version: str
    selection_seed: int  # = effective_seed (compat)
    root_seed: int | str | None
    effective_seed: int
    seed_resolution: dict[str, Any]
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
    discovery_method: str = DISCOVERY_METHOD_V2
    evidence_hash: str | None = None
    intent_breakdown: dict[str, int] = field(default_factory=dict)
    topic_breakdown: dict[str, int] = field(default_factory=dict)
    entity_breakdown: dict[str, int] = field(default_factory=dict)
    paid_retrieval_opt_in: bool = False
    paid_retrieval_ready: bool = False
    intent_budget_id: str = INTENT_BUDGET_ID
    intent_budget_policy: dict[str, Any] = field(default_factory=dict)
    quality_version: str = QUALITY_VERSION
    mmr_lambda: float = DEFAULT_MMR_LAMBDA
    max_per_topic: int = DEFAULT_MAX_PER_TOPIC
    grace_mode: bool = False
    content_hash: str | None = None
    fingerprint: str | None = None
    representativeness: dict[str, Any] = field(default_factory=dict)
    generator_version: str = "candidate-gen-v2"
    dedup_method: str = "lexical_jaccard_v1"

    def to_dict(self) -> dict[str, Any]:
        return {
            "query_set_id": self.query_set_id,
            "query_set_version": self.query_set_version,
            "selection_seed": self.selection_seed,
            "root_seed": self.root_seed,
            "effective_seed": self.effective_seed,
            "seed_resolution": self.seed_resolution,
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
            "intent_budget_id": self.intent_budget_id,
            "intent_budget_policy": self.intent_budget_policy,
            "quality_version": self.quality_version,
            "mmr_lambda": self.mmr_lambda,
            "max_per_topic": self.max_per_topic,
            "grace_mode": self.grace_mode,
            "content_hash": self.content_hash,
            "fingerprint": self.fingerprint,
            "representativeness": self.representativeness,
            "generator_version": self.generator_version,
            "dedup_method": self.dedup_method,
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


def _set_id(seed: int, evidence_hash: str | None, version: str) -> str:
    h = hashlib.sha256(f"{seed}|{evidence_hash}|{version}".encode()).hexdigest()[:12]
    return f"qs_{h}"


def fingerprint_members(members: list[QuerySetMember]) -> str:
    payload = [
        {
            "query_id": m.query.query_id,
            "text": m.query.text,
            "intent": m.query.intent,
            "topic": m.query.topic,
            "entity": m.query.entity,
        }
        for m in members
    ]
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode()).hexdigest()


def content_hash_for_set(
    *,
    evidence_hash: str | None,
    effective_seed: int,
    version: str,
    fingerprint: str,
) -> str:
    raw = f"{evidence_hash}|{effective_seed}|{version}|{fingerprint}"
    return hashlib.sha256(raw.encode()).hexdigest()[:24]


def _breakdown(
    members: list[QuerySetMember],
) -> tuple[dict[str, int], dict[str, int], dict[str, int]]:
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


def _rel_score(q: CandidateQuery, profile_tokens: set[str]) -> float:
    qtoks = tokenize(q.text)
    if not qtoks:
        return 0.0
    overlap = len(qtoks & profile_tokens) / max(len(qtoks), 1)
    return 0.6 * float(q.confidence) + 0.4 * overlap


def _mmr_pick(
    pool: list[CandidateQuery],
    selected: list[CandidateQuery],
    profile_tokens: set[str],
    *,
    lam: float,
) -> CandidateQuery | None:
    if not pool:
        return None
    best: CandidateQuery | None = None
    best_score = -math.inf
    for q in pool:
        rel = _rel_score(q, profile_tokens)
        if not selected:
            sim = 0.0
        else:
            sim = max(
                jaccard(tokenize(q.text), tokenize(s.text)) for s in selected
            )
        score = lam * rel - (1.0 - lam) * sim
        # Deterministic tie-break: higher score, then lower query_id
        key = (score, -ord(q.query_id[0]) if q.query_id else 0)
        if score > best_score or (
            math.isclose(score, best_score) and best is not None and q.query_id < best.query_id
        ):
            best_score = score
            best = q
        elif best is None:
            best = q
            best_score = score
        _ = key
    return best


def select_query_set_v2(
    accepted: list[tuple[CandidateQuery, GateDecision]],
    *,
    understanding: SiteUnderstanding,
    top_k: int = DEFAULT_TOP_K,
    seed_resolution: SeedResolution,
    candidates_count: int = 0,
    rejected_count: int = 0,
    paid_retrieval_opt_in: bool = False,
    target_site_audit: dict[str, Any] | None = None,
    mmr_lambda: float = DEFAULT_MMR_LAMBDA,
    max_per_topic: int | None = None,
    grace_mode: bool = False,
    frozen_at: str | None = None,
    dedup_method: str = "lexical_jaccard_v1",
) -> QuerySetV3:
    """Coverage-aware deterministic selection with hard intent budgets."""
    k = max(MIN_TOP_K, min(int(top_k), MAX_TOP_K))
    seed = seed_resolution.effective_seed
    warnings = list(understanding.warnings or [])
    warnings.extend(seed_resolution.warnings)
    if grace_mode:
        warnings.append("SMALL_SITE_POOL")

    topic_cap = max_per_topic
    if topic_cap is None:
        # ≤3–4 per topic in k≈20; scale lightly
        topic_cap = max(2, min(4, int(math.ceil(k / 6))))

    policy = build_intent_budget_policy(
        site_genre=understanding.site_genre,
        top_k=k,
        has_commercial=bool(understanding.commercial_intents),
    )

    empty_kwargs: dict[str, Any] = dict(
        query_set_id=_set_id(seed, understanding.evidence_hash, QUERY_SET_VERSION),
        query_set_version=QUERY_SET_VERSION,
        selection_seed=seed,
        root_seed=seed_resolution.root_seed,
        effective_seed=seed,
        seed_resolution=seed_resolution.to_dict(),
        selection_method=SELECTION_METHOD,
        candidates_count=candidates_count,
        accepted_count=0,
        rejected_count=rejected_count,
        profile_snapshot=understanding.structured or {},
        target_site_audit=target_site_audit or {},
        warnings=warnings + ["no_accepted_candidates"],
        frozen_at=frozen_at,
        evidence_hash=understanding.evidence_hash,
        paid_retrieval_opt_in=False,
        paid_retrieval_ready=False,
        intent_budget_policy=policy.to_dict(),
        grace_mode=grace_mode,
        mmr_lambda=mmr_lambda,
        max_per_topic=topic_cap,
        dedup_method=dedup_method,
    )

    if not accepted:
        return QuerySetV3(
            status="insufficient_evidence" if candidates_count else "empty",
            members=[],
            **empty_kwargs,
        )

    gate_by_id = {q.query_id: g for q, g in accepted}
    # Stable order: confidence desc, query_id asc — no wall-clock / random
    unique = sorted(
        [q for q, _ in accepted],
        key=lambda q: (-q.confidence, q.query_id),
    )

    profile_tokens: set[str] = set()
    for t in understanding.topics:
        profile_tokens |= tokenize(t)
    if understanding.organization_brand:
        profile_tokens |= tokenize(understanding.organization_brand)

    by_intent: dict[str, list[CandidateQuery]] = {i: [] for i in STRATA_ORDER}
    for q in unique:
        by_intent.setdefault(q.intent, []).append(q)

    selected: list[CandidateQuery] = []
    rationales: dict[str, str] = {}
    used_ids: set[str] = set()
    topic_counts: dict[str, int] = {}
    intent_counts: dict[str, int] = {i: 0 for i in STRATA_ORDER}
    covered_cells: set[tuple[str, str]] = set()

    def can_take(q: CandidateQuery) -> bool:
        if q.query_id in used_ids:
            return False
        t = q.topic or "_none"
        if topic_counts.get(t, 0) >= topic_cap:
            return False
        budget = policy.for_intent(q.intent)
        if intent_counts.get(q.intent, 0) >= budget.max_count:
            return False
        return True

    def take(q: CandidateQuery, why: str) -> None:
        selected.append(q)
        used_ids.add(q.query_id)
        t = q.topic or "_none"
        topic_counts[t] = topic_counts.get(t, 0) + 1
        intent_counts[q.intent] = intent_counts.get(q.intent, 0) + 1
        covered_cells.add((t, q.intent))
        rationales[q.query_id] = why

    # Pass 1: satisfy intent minima with new coverage cells preferred
    for intent in STRATA_ORDER:
        budget = policy.for_intent(intent)
        while intent_counts.get(intent, 0) < budget.min_count and len(selected) < k:
            pool = [q for q in by_intent.get(intent, []) if can_take(q)]
            if not pool:
                warnings.append(f"INTENT_BUDGET_SHORTFALL:{intent}")
                break
            pool.sort(
                key=lambda q: (
                    0 if (q.topic or "_none", q.intent) not in covered_cells else 1,
                    -_rel_score(q, profile_tokens),
                    q.query_id,
                )
            )
            take(pool[0], f"intent_min:{intent}")

    # Pass 2: fill remaining slots via MMR under caps
    while len(selected) < k:
        pool = [q for q in unique if can_take(q)]
        if not pool:
            break
        # Prefer uncovered (topic, intent) cells
        uncovered = [
            q
            for q in pool
            if (q.topic or "_none", q.intent) not in covered_cells
        ]
        focus = uncovered or pool
        pick = _mmr_pick(focus, selected, profile_tokens, lam=mmr_lambda)
        if pick is None:
            break
        take(pick, "mmr_coverage")

    # Pass 3: if still short (small pools), relax intent max only (keep topic cap)
    if len(selected) < k:
        relaxed = [
            q
            for q in unique
            if q.query_id not in used_ids
            and topic_counts.get(q.topic or "_none", 0) < topic_cap
        ]
        relaxed.sort(key=lambda q: (-_rel_score(q, profile_tokens), q.query_id))
        for q in relaxed:
            if len(selected) >= k:
                break
            take(q, "fill_relaxed_intent_max")

    # Concentration warning
    if selected:
        top_share = max(topic_counts.values()) / len(selected)
        if top_share > 0.40:
            warnings.append("TOPIC_CONCENTRATION")

    members = [
        QuerySetMember(
            query=q,
            gate=gate_by_id[q.query_id],
            selection_rank=i + 1,
            selection_rationale=rationales.get(q.query_id, ""),
        )
        for i, q in enumerate(selected[:k])
    ]
    intents, topics, entities = _breakdown(members)
    fp = fingerprint_members(members)
    ch = content_hash_for_set(
        evidence_hash=understanding.evidence_hash,
        effective_seed=seed,
        version=QUERY_SET_VERSION,
        fingerprint=fp,
    )
    ready = len(members) >= MIN_TOP_K

    return QuerySetV3(
        query_set_id=_set_id(seed, understanding.evidence_hash, QUERY_SET_VERSION),
        query_set_version=QUERY_SET_VERSION,
        selection_seed=seed,
        root_seed=seed_resolution.root_seed,
        effective_seed=seed,
        seed_resolution=seed_resolution.to_dict(),
        selection_method=SELECTION_METHOD,
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
        frozen_at=frozen_at,
        discovery_method=DISCOVERY_METHOD_V2,
        evidence_hash=understanding.evidence_hash,
        intent_breakdown=intents,
        topic_breakdown=topics,
        entity_breakdown=entities,
        paid_retrieval_opt_in=bool(paid_retrieval_opt_in),
        paid_retrieval_ready=bool(paid_retrieval_opt_in) and ready,
        intent_budget_policy=policy.to_dict(),
        grace_mode=grace_mode,
        content_hash=ch,
        fingerprint=fp,
        mmr_lambda=mmr_lambda,
        max_per_topic=topic_cap,
        dedup_method=dedup_method,
    )


# Keep QUERY_DISCOVERY_METHOD import used for compat docs
_ = QUERY_DISCOVERY_METHOD
