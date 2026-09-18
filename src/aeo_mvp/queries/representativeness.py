"""Representativeness report ``representativeness-v1`` (Phase 4).

Diagnostic metadata only — not ranking, not a site quality score.
"""

from __future__ import annotations

from typing import Any

from aeo_mvp.queries.generate import CandidateQuery
from aeo_mvp.queries.quality import GateDecision
from aeo_mvp.queries.select_v2 import QuerySetMember, QuerySetV3
from aeo_mvp.understanding.site import SiteUnderstanding

REPORT_VERSION = "representativeness-v1"


def build_representativeness_report(
    *,
    understanding: SiteUnderstanding,
    candidates: list[CandidateQuery],
    accepted: list[tuple[CandidateQuery, GateDecision]],
    rejected: list[tuple[CandidateQuery, GateDecision]],
    query_set: QuerySetV3,
    redundancy_groups: list[list[str]] | None = None,
) -> dict[str, Any]:
    available_topics = []
    seen: set[str] = set()
    for t in understanding.topics:
        key = (t or "").strip().lower()
        if not key or key in seen:
            continue
        seen.add(key)
        available_topics.append(t)

    selected_topics = {
        (m.query.topic or "").strip()
        for m in query_set.members
        if m.query.topic
    }
    covered = []
    uncovered = []
    for t in available_topics:
        # soft match: selected topic phrase appears in evidence topic or vice versa
        hit = False
        tl = t.lower()
        for st in selected_topics:
            sl = st.lower()
            if sl[:24] in tl or tl[:24] in sl:
                hit = True
                break
        if hit:
            covered.append(t)
        else:
            uncovered.append(t)

    intent_policy = (query_set.intent_budget_policy or {}).get("budgets") or []
    intent_coverage: dict[str, Any] = {}
    for b in intent_policy:
        intent = b["intent"]
        actual = query_set.intent_breakdown.get(intent, 0)
        intent_coverage[intent] = {
            "actual": actual,
            "min": b.get("min_count"),
            "max": b.get("max_count"),
            "shortfall": max(0, int(b.get("min_count") or 0) - actual),
        }

    entity_available = []
    if understanding.organization_brand:
        entity_available.append(understanding.organization_brand)
    entity_available.extend(
        [p for p in understanding.products_services if not str(p).startswith("#")][:8]
    )
    selected_entities = {
        (m.query.entity or "").strip()
        for m in query_set.members
        if m.query.entity
    }
    entities_covered = [e for e in entity_available if e in selected_entities]

    reject_reasons: dict[str, int] = {}
    for _q, d in rejected:
        for r in d.reasons:
            key = r.split(":")[0] if r else "unknown"
            reject_reasons[key] = reject_reasons.get(key, 0) + 1

    selection_rationale = [
        {
            "query_id": m.query.query_id,
            "rank": m.selection_rank,
            "rationale": m.selection_rationale,
            "intent": m.query.intent,
            "topic": m.query.topic,
        }
        for m in query_set.members
    ]

    topic_ratio = (
        len(covered) / len(available_topics) if available_topics else 0.0
    )

    return {
        "report_version": REPORT_VERSION,
        "counts": {
            "candidates": len(candidates),
            "accepted": len(accepted),
            "rejected": len(rejected),
            "selected": len(query_set.members),
        },
        "topic_coverage": {
            "covered": len(covered),
            "available": len(available_topics),
            "ratio": round(topic_ratio, 3),
            "uncovered_topics": uncovered[:12],
            "covered_topics": covered[:12],
        },
        "intent_coverage": intent_coverage,
        "entity_coverage": {
            "covered": len(entities_covered),
            "available": len(entity_available),
            "covered_entities": entities_covered[:8],
        },
        "max_per_topic": query_set.max_per_topic,
        "rejected_reasons": reject_reasons,
        "redundancy_groups": redundancy_groups or [],
        "selection_rationale": selection_rationale,
        "quality_diagnostics": {
            "quality_version": query_set.quality_version,
            "fingerprint": query_set.fingerprint,
        },
        "warnings": list(query_set.warnings),
        "grace_mode": query_set.grace_mode,
        "note": "Diagnostic metadata only — not a ranking or site quality score",
    }
