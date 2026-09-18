"""Intent budget policy ``intent-budget-v1`` (Phase 4).

Hard min/max per intent, genre-conditioned. Commercial may be 0 without failure
when monetization evidence is absent.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

INTENT_BUDGET_ID = "intent-budget-v1"

# (min, max) for k≈20. Budgets scale linearly with top_k.
_BUDGETS: dict[str, dict[str, tuple[int, int]]] = {
    "personal_tech_blog": {
        "informational": (5, 7),
        "problem_solving": (4, 6),
        "recommendation": (2, 4),
        "comparison": (2, 3),
        "navigational": (1, 2),
        "commercial": (0, 1),
    },
    "saas_product": {
        "informational": (3, 5),
        "problem_solving": (3, 5),
        "recommendation": (2, 4),
        "comparison": (2, 4),
        "navigational": (1, 2),
        "commercial": (2, 4),
    },
    "documentation": {
        "informational": (6, 9),
        "problem_solving": (5, 8),
        "recommendation": (1, 2),
        "comparison": (1, 2),
        "navigational": (1, 2),
        "commercial": (0, 1),
    },
    "ecommerce": {
        "informational": (2, 4),
        "problem_solving": (2, 3),
        "recommendation": (3, 5),
        "comparison": (2, 4),
        "navigational": (1, 2),
        "commercial": (4, 7),
    },
    "default": {
        "informational": (4, 7),
        "problem_solving": (3, 6),
        "recommendation": (2, 4),
        "comparison": (2, 3),
        "navigational": (1, 2),
        "commercial": (0, 2),
    },
}

STRATA_ORDER = [
    "informational",
    "problem_solving",
    "recommendation",
    "comparison",
    "navigational",
    "commercial",
]


@dataclass
class IntentBudget:
    intent: str
    min_count: int
    max_count: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class IntentBudgetPolicy:
    policy_id: str
    genre: str
    top_k: int
    budgets: list[IntentBudget] = field(default_factory=list)
    allow_commercial: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "policy_id": self.policy_id,
            "genre": self.genre,
            "top_k": self.top_k,
            "allow_commercial": self.allow_commercial,
            "budgets": [b.to_dict() for b in self.budgets],
        }

    def for_intent(self, intent: str) -> IntentBudget:
        for b in self.budgets:
            if b.intent == intent:
                return b
        return IntentBudget(intent=intent, min_count=0, max_count=self.top_k)


def _scale(lo: int, hi: int, top_k: int, base_k: int = 20) -> tuple[int, int]:
    if top_k == base_k:
        return lo, hi
    scale = top_k / base_k
    return max(0, int(round(lo * scale))), max(0, int(round(hi * scale)))


def resolve_genre_key(site_genre: str | None) -> str:
    g = (site_genre or "").strip().lower()
    if g in _BUDGETS:
        return g
    if g in ("personal_blog", "blog", "personal_tech_blog"):
        return "personal_tech_blog"
    if g in ("saas", "saas_product", "b2b_saas"):
        return "saas_product"
    if g in ("docs", "documentation", "developer_docs"):
        return "documentation"
    if g in ("ecommerce", "e-commerce", "shop"):
        return "ecommerce"
    return "default"


def build_intent_budget_policy(
    *,
    site_genre: str | None,
    top_k: int,
    has_commercial: bool = False,
) -> IntentBudgetPolicy:
    genre_key = resolve_genre_key(site_genre)
    raw = _BUDGETS[genre_key]
    budgets: list[IntentBudget] = []
    allow_commercial = bool(has_commercial) or genre_key in (
        "saas_product",
        "ecommerce",
    )
    for intent in STRATA_ORDER:
        lo, hi = raw.get(intent, (0, top_k))
        lo, hi = _scale(lo, hi, top_k)
        if intent == "commercial" and not allow_commercial:
            lo, hi = 0, 0
        budgets.append(IntentBudget(intent=intent, min_count=lo, max_count=hi))
    return IntentBudgetPolicy(
        policy_id=INTENT_BUDGET_ID,
        genre=genre_key,
        top_k=top_k,
        budgets=budgets,
        allow_commercial=allow_commercial,
    )
