"""health-v1 aggregation formulas."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from sqlalchemy.orm import Session

from aeo_mvp.config import HEALTH_FORMULA_VERSION
from aeo_mvp.db.models import ScoreComponent, new_id

WEIGHTS = {
    "technical": 0.25,
    "content": 0.25,
    "entity": 0.20,
    "structured_data": 0.15,
    "answerability": 0.15,
}


def clamp(x: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, x))


def health_from_components(
    technical: float,
    content: float,
    entity: float,
    structured_data: float,
    answerability: float,
) -> float:
    """Compute H from component scores (worked example locked in tests)."""
    h = (
        WEIGHTS["technical"] * technical
        + WEIGHTS["content"] * content
        + WEIGHTS["entity"] * entity
        + WEIGHTS["structured_data"] * structured_data
        + WEIGHTS["answerability"] * answerability
    )
    return clamp(h)


@dataclass
class HealthResult:
    health: float
    components: dict[str, float]
    formula_version: str = HEALTH_FORMULA_VERSION


def compute_health(
    session: Session,
    job_id: str,
    *,
    technical: float,
    content: float,
    entity: float,
    structured_data: float,
    answerability: float,
    breakdowns: dict[str, dict[str, Any]] | None = None,
    provenance: str = "derived_metric",
) -> HealthResult:
    components = {
        "technical": clamp(technical),
        "content": clamp(content),
        "entity": clamp(entity),
        "structured_data": clamp(structured_data),
        "answerability": clamp(answerability),
    }
    health = health_from_components(**components)
    breakdowns = breakdowns or {}

    for name, score in components.items():
        session.add(
            ScoreComponent(
                id=new_id(),
                job_id=job_id,
                component=name,
                score=score,
                formula_version=HEALTH_FORMULA_VERSION,
                breakdown_json=json.dumps(breakdowns.get(name, {}), sort_keys=True),
                provenance=provenance,
            )
        )
    session.add(
        ScoreComponent(
            id=new_id(),
            job_id=job_id,
            component="health",
            score=health,
            formula_version=HEALTH_FORMULA_VERSION,
            breakdown_json=json.dumps(
                {"weights": WEIGHTS, "components": components},
                sort_keys=True,
            ),
            provenance=provenance,
        )
    )
    session.flush()
    return HealthResult(health=health, components=components)
