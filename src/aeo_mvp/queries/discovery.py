"""Query discovery from site understanding (P1-C)."""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from typing import Any, Literal

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
]

DEFAULT_TOP_N = 10
MIN_TOP_N = 8
MAX_TOP_N = 12


@dataclass
class DiscoveredQuery:
    id: str
    query: str
    classification: QueryClass
    intent: str
    source: str = "site_understanding"
    score: float = 1.0

    def to_prompt(self) -> dict[str, str]:
        return {"id": self.id, "query": self.query, "intent": self.classification}


@dataclass
class DiscoveryResult:
    queries: list[DiscoveredQuery] = field(default_factory=list)
    candidates_count: int = 0
    selected_count: int = 0
    method: str = "deterministic_v1"
    provenance: str = "derived_metric"
    fallback_used: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "method": self.method,
            "provenance": self.provenance,
            "fallback_used": self.fallback_used,
            "candidates_count": self.candidates_count,
            "selected_count": self.selected_count,
            "queries": [asdict(q) for q in self.queries],
        }

    def as_prompts(self) -> list[dict[str, str]]:
        return [q.to_prompt() for q in self.queries]


def _norm_query(q: str) -> str:
    return re.sub(r"\s+", " ", q.lower().strip())


def _classify_and_candidates(u: SiteUnderstanding) -> list[DiscoveredQuery]:
    brand = (u.organization_brand or "").strip()
    industry = (u.industry_category_guess or "software").replace("_", " ")
    product = u.products_services[0] if u.products_services else industry
    audience = u.audience_hints[0] if u.audience_hints else "teams"
    topics = u.topics[:3]
    out: list[DiscoveredQuery] = []
    n = 0

    def add(classification: QueryClass, query: str, score: float = 1.0) -> None:
        nonlocal n
        n += 1
        out.append(
            DiscoveredQuery(
                id=f"dq{n}_{classification}",
                query=query,
                classification=classification,
                intent=classification,
                score=score,
            )
        )

    if brand:
        add("brand", f"What is {brand}?", 1.0)
        add("informational", f"What does {brand} do?", 0.95)
        add("product_service", f"What products or services does {brand} offer?", 0.9)
        add("alternatives", f"What are alternatives to {brand}?", 0.85)
        add("comparison", f"How does {brand} compare to other {industry} tools?", 0.85)
        add("commercial", f"How much does {brand} cost?", 0.8)
        add("best_for", f"Is {brand} good for {audience}?", 0.8)
        add(
            "problem_solution",
            f"How can {brand} help with {product}?",
            0.75,
        )
        add("audience", f"Who is {brand} for?", 0.7)
    else:
        add("informational", f"What are leading options for {industry}?", 0.7)

    # Topic-driven informational / problem queries
    for t in topics:
        t_clean = t.rstrip("?")
        if len(t_clean) < 8:
            continue
        if t_clean.endswith("?") or re.match(
            r"^(who|what|when|where|why|how)\b", t_clean, re.I
        ):
            add("informational", t_clean if t_clean.endswith("?") else t_clean + "?", 0.65)
        else:
            add("problem_solution", f"How does {t_clean} work?", 0.55)

    if u.commercial_intents:
        add(
            "commercial",
            f"Where can I buy or start a trial for {brand or product}?",
            0.7,
        )

    add("best_for", f"What is the best {industry} tool for {audience}?", 0.6)
    add("comparison", f"How do teams evaluate tools in {industry}?", 0.6)
    return out


def dedupe_queries(candidates: list[DiscoveredQuery]) -> list[DiscoveredQuery]:
    seen: set[str] = set()
    out: list[DiscoveredQuery] = []
    for q in sorted(candidates, key=lambda x: (-x.score, x.id)):
        key = _norm_query(q.query)
        if key in seen:
            continue
        seen.add(key)
        out.append(q)
    return out


def select_top_n(
    queries: list[DiscoveredQuery], top_n: int = DEFAULT_TOP_N
) -> list[DiscoveredQuery]:
    n = max(MIN_TOP_N, min(int(top_n), MAX_TOP_N))
    # Prefer diverse classifications
    selected: list[DiscoveredQuery] = []
    used_classes: set[str] = set()
    remaining = list(queries)
    # Pass 1: one per class
    for q in list(remaining):
        if q.classification in used_classes:
            continue
        selected.append(q)
        used_classes.add(q.classification)
        remaining.remove(q)
        if len(selected) >= n:
            return selected[:n]
    # Pass 2: fill by score
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
) -> DiscoveryResult:
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
        )
    candidates = _classify_and_candidates(understanding)  # type: ignore[arg-type]
    deduped = dedupe_queries(candidates)
    selected = select_top_n(deduped, top_n=top_n)
    return DiscoveryResult(
        queries=selected,
        candidates_count=len(candidates),
        selected_count=len(selected),
        provenance=provenance,
        fallback_used=False,
    )


def discovery_to_json(result: DiscoveryResult) -> str:
    return json.dumps(result.to_dict(), sort_keys=True)
