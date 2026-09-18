"""Persist query sets onto experiment configs / report sections."""

from __future__ import annotations

import json
from typing import Any

from aeo_mvp.queries.select import QuerySet


def query_set_to_json(qs: QuerySet) -> str:
    return json.dumps(qs.to_dict(), sort_keys=True)


def query_set_summary(qs: QuerySet) -> dict[str, Any]:
    """Compact summary for reports / verification (descriptive metrics only)."""
    d = qs.to_dict() if hasattr(qs, "to_dict") else {}
    base = {
        "query_set_id": getattr(qs, "query_set_id", None),
        "query_set_version": getattr(qs, "query_set_version", None),
        "status": getattr(qs, "status", None),
        "selection_seed": getattr(qs, "selection_seed", None),
        "selection_method": getattr(qs, "selection_method", None),
        "candidates_count": getattr(qs, "candidates_count", 0),
        "accepted_count": getattr(qs, "accepted_count", 0),
        "rejected_count": getattr(qs, "rejected_count", 0),
        "selected_count": len(getattr(qs, "members", []) or []),
        "intent_breakdown": getattr(qs, "intent_breakdown", {}),
        "topic_breakdown": {
            k: v
            for k, v in list(getattr(qs, "topic_breakdown", {}).items())[:12]
        },
        "entity_breakdown": {
            k: v
            for k, v in list(getattr(qs, "entity_breakdown", {}).items())[:8]
        },
        "paid_retrieval_opt_in": getattr(qs, "paid_retrieval_opt_in", False),
        "paid_retrieval_ready": getattr(qs, "paid_retrieval_ready", False),
        "discovery_method": getattr(qs, "discovery_method", None),
        "evidence_hash": getattr(qs, "evidence_hash", None),
        "warnings": list(getattr(qs, "warnings", []) or [])[:12],
        "frozen_at": getattr(qs, "frozen_at", None),
    }
    # Phase 4 additive (ignored by older readers)
    for key in (
        "root_seed",
        "effective_seed",
        "seed_resolution",
        "fingerprint",
        "content_hash",
        "grace_mode",
        "intent_budget_id",
        "quality_version",
        "mmr_lambda",
        "max_per_topic",
    ):
        if key in d:
            base[key] = d[key]
        elif hasattr(qs, key):
            base[key] = getattr(qs, key)
    return base
