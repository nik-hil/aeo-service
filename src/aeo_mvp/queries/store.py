"""Persist query sets onto experiment configs / report sections."""

from __future__ import annotations

import json
from typing import Any

from aeo_mvp.queries.select import QuerySet


def query_set_to_json(qs: QuerySet) -> str:
    return json.dumps(qs.to_dict(), sort_keys=True)


def query_set_summary(qs: QuerySet) -> dict[str, Any]:
    """Compact summary for reports / verification (descriptive metrics only)."""
    return {
        "query_set_id": qs.query_set_id,
        "query_set_version": qs.query_set_version,
        "status": qs.status,
        "selection_seed": qs.selection_seed,
        "selection_method": qs.selection_method,
        "candidates_count": qs.candidates_count,
        "accepted_count": qs.accepted_count,
        "rejected_count": qs.rejected_count,
        "selected_count": len(qs.members),
        "intent_breakdown": qs.intent_breakdown,
        "topic_breakdown": {
            k: v for k, v in list(qs.topic_breakdown.items())[:12]
        },
        "entity_breakdown": {
            k: v for k, v in list(qs.entity_breakdown.items())[:8]
        },
        "paid_retrieval_opt_in": qs.paid_retrieval_opt_in,
        "paid_retrieval_ready": qs.paid_retrieval_ready,
        "discovery_method": qs.discovery_method,
        "evidence_hash": qs.evidence_hash,
        "warnings": qs.warnings[:12],
        "frozen_at": qs.frozen_at,
    }
